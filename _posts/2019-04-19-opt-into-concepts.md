---
layout: post
title: "Opting into Concepts"
category: c++
tags:
 - c++
 - concepts
pubdraft: yes
--- 

When we write types, we sometimes find ourselves wanting to write functionality that opts in to a particular concept (which, with C++20, will also become `concept`{:.language-cpp}). For the purposes of this post, I want to focus specifically on those cases where the type author is very clearly intending to opt-in to a known concept -- as opposed to writing logic that happens to satisfy a concept that the type author may not even have been aware of. The most familiar and easily recognizable examples of what I mean are:

- Printable (I want to make it possible `std::cout`{:.language-cpp} my type)
- EqualityComparable and Ordered (I want to make it possible to compare my type using `==`{:.language-cpp} or `<`{:.language-cpp})
- Range (I want to be able to iterate over my type)

Now these are all well-established concepts, they all must be opted into, and we are pretty explicit when we opt into them.  While we know how to make our types satisfy those concepts today, let's just throw that knowledge out temporarily. C++ actually provides a lot of ways for us to create new concepts for type authors to opt into, and I thought it'd be interesting to go through what those methods are and what the properties of those methods are, and see what we can do with the above four and what kinds of insights we can glean.

### Inheritance

The classic, object-oriented approach to this is of course: inheritance. The concept author writes a class that has some pure `virtual`{:.language-cpp} member functions in it, and type authors inherit from those interfaces and fill in as appropriate. We could provide a `Printable` interface like so (let's simplify `std::ostream`{:.language-cpp} for the sake of example):

```cpp
namespace std {
    struct ostream;

    struct Printable {
        virtual void print(ostream&) const = 0;
    };

    struct ostream {
        ostream& operator<<(Printable const& p) {
            p.print(*this);
            return *this;
        }
        
        // other types, etc.
        ostream& operator<<(char);
        ostream& operator<<(int);
        // ...
    };
}
```

Now, if I want to make a type that is `std::cout`{:.language-cpp}-able, I must inherit from `std::Printable`{:.language-cpp} and implement `print`:

```cpp
class SeqNum : public std::Printable
{
public:
    void print(std::ostream& os) const override {
        os << "SeqNum(" << value << ")";
    }
private:
    int value;
};
```

This isn't what most people would consider to be modern C++, and isn't the way we solve this problem today, but it does work. Let's consider the salient features of this approach.

It's a very <span class="token important">explicit</span> opt-in, the only way for `SeqNum` to satisfy `std::Printable`{:.language-cpp} is to inherit from it. That's not going to happen by accident. It's also <span class="token important">intrusive</span> - you have to modify the class itself to add this behavior, both because you need to inherit and to add member functions. An intrusive approach is inherently extremely limiting - can't satisfy concepts for any fundamental types or arrays, or any types you don't own. 

However, this gives us the benefit that the operations we need to customize are <span class="token important">checked early</span>. There are two different things I mean when I want to talk about early checking, directed towards two different people:

- for the type author: to ensure that the concept was correctly opted into. In this case, if we got the signature to `print()`{:.language-cpp} wrong, that would be a compiler error at the point of definition. If we forgot to override a function entirely, that would be a compile error when we try to construct a `SeqNum` - with a clearly enumerated list of virtual functions we missed.
- for the algorithm author: to ensure that the interface is used properly. In this case, if we wrote a function that took a `std::Printable const& p`{:.language-cpp} to apply to any printable type, and tried to write `p.print()`{:.language-cpp} or `p.display()`{:.language-cpp}, those would be compiler errors at the point of definition of the function - rather than at its point of use.

Let's pick a different concept: equality comparable. Here's how we might implement that a classical, object-oriented interface (there may be a better way to do this, specifically, but hopefully this is sufficiently illustrative):

```cpp
template <typename T>
struct Eq {
    virtual bool operator==(T const& rhs) const {
        return equals(rhs);
    }
    virtual bool operator!=(T const& rhs) const {
        return !equals(rhs);
    }
private:
    virtual bool equals(T const& rhs) const = 0;
};
```
which we would similarly opt-in to with our `SeqNum` type like:
```cpp
class SeqNum : public Eq<SeqNum>
{
private:
    bool equals(SeqNum const& rhs) const override {
        return value == rhs.value;
    }
    int value;
};
```

What the inheritance approach gives us here additionally are <span class="token important">associated functions</span> that we can call with nice syntax. To opt-in to the concept `Eq`, we have to provide one customization point - `equals()`{:.language-cpp} - which we do in order to get two nice, useful functions - `==`{:.language-cpp} and `!=`{:.language-cpp}. This can easily stack as well:

```cpp
typename <typename T>
struct Ord : Eq {
    virtual bool operator<(T const& rhs) const {
        return compare(rhs) < 0;
    }
    virtual bool operator>(T const& rhs) const {
        return compare(rhs) > 0;
    }
    virtual bool operator<=(T const& rhs) const {
        return compare(rhs) <= 0;
    }
    virtual bool operator>=(T const& rhs) const {
        return compare(rhs) >= 0;
    }    
private:
    virtual int compare(T const& rhs) const = 0;
};
```

Now, if I want all six comparisons, I <span class="token important">explicitly</span> and <span class="token important">intrusively</span> inherit from `Ord<T>`{:.language-cpp}, I get the compiler to ensure that I did everything right because my work is <span class="token important">checked early</span>. And for my efforts, I get six <span class="token important">associated functions</span> that I can use with nice syntax.

This gets much more awkward when concepts need to be more parameterized. Take `Range`. The C++ abstraction is that we need a `begin()` and an `end()` - which as of C++17 can be different types. I guess that would be something like:

```cpp
template <typename Iterator, typename Sentinel = Iterator>
struct ConstRange {
    using const_iterator = Iterator;

    virtual Iterator begin() const = 0;
    virtual Sentinel end() const = 0;
};

template <typename Iterator, typename Sentinel = Iterator>
struct Range {
    using iterator = Iterator;

    virtual Iterator begin() = 0;
    virtual Sentinel end() = 0;
};

template <typename T>
class MyVec : public Range<T*>
            , public ConstRange<T const*>
{
public:
    T*       begin()       override { return begin_; }
    T const* begin() const override { return begin_; }
    T*       end()         override { return end_; }
    T const* end()   const override { return end_; }
    
private:
    T* begin_;
    T* end_;
    T* capacity_;
};
```

This may look a bit silly (or at least jarring), but there is one nice thing that we would be able to do with this model: have the chaining we all want. In the same way `Eq` provides `==`{:.language-cpp} and `!=`{:.language-cpp}, `Range` could provide tons of adapters:

```cpp
template <typename Iterator, typename Sentinel = Iterator>
struct Range {
    using iterator = iterator;
    using value_type = value_type_t<Iterator>;
    virtual Iterator begin() = 0;
    virtual Sentinel end() = 0;
    
    auto filter(Predicate<value_type> auto&&) const;
    auto transform(Invocable<value_type> auto&&) const;
    auto take(size_t ) const;
    auto drop(size_t ) const;
    auto take_while(Predicate<value_type> auto&&) const;
    auto drop_while(Predicate<value_type> auto&&) const;
    auto accumulate() const;
    // ...
};
```

And now any `Range` at all can do things like `rng.filter(f).transform(g).take(5).accumulate()`{:.language-cpp}. Don't think too hard about the performance of such a model just yet. 

### Template Specialization

A different approach entirely to how to specify concepts would be rather than requiring that a type inherit from some base class that it instead specialize some template. If this sounds a little unfamiliar at first, there are actually multiple examples of this in the standard library - this is how you opt-in to being Hashable with `std::hash`{:.language-cpp} and how you opt-in to being TupleLike for standard bindings with `std::tuple_size`{:.language-cpp} and `std::tuple_element`{:.language-cpp}.

Going back to `Printable`, that might be implemented like:

```cpp
namespace std {
    template <typename T>
    struct Printable;
    
    // some specializations out of the box
    template <> struct Printable<char> { /* ... */ };
    template <> struct Printable<int>  { /* ... */ };
    // ...

    struct ostream {        
        template <typename T>
        ostream& operator<<(T const& p) {
            Printable<T>::print(*this, p);
            return *this;
        }
    };
}
```

which we would opt in like:

```cpp
struct SeqNum {
    int value;
};

template <>
struct std::Printable<SeqNum> {
    static void print(std::ostream& os, SeqNum const& s) {
        os << "SeqNum(" << s.value << ")";
    }
};
```

How does this approach compare to the inheritance approach? Yes, it removes the virtual dispatch but I'm not super concerned with that at this point. This is still an <span class="token important">explicit</span> opt-in - you have to manually specialize the type which acts like the concept. But a key difference is that it's <span class="token important">unobtrusive</span> - I don't need to modify `SeqNum` itself to get this functionality, I can do so externally. This is an enormous benefit!

Also nothing in the language itself prevents me from doing a "bad" specialization - one that either gets signatures wrong or misses things entirely. That's because while virtual functions are baked into the language, specialization like this is just a convention. Nor does anything in the language prevent me from trying to write an invalid operation for this type - I can write `Printable<T>::display(x)`{:.language-cpp} (an invalid function) or `Printable<T>::print(x, std::cout)`{:.language-cpp} (wrong order of arguments). All of these mistakes will only be caught at the point of use - they are <span class="token important">checked late</span>.

This approach also suffers from not having an ergonomic syntax. Consider hashing. With the inheritance approach, given some object that satisfied the concept, we would write:

```cpp
obj.hash()
```

With the specialization approach, we would write:

```cpp
std::hash<decltype(obj)>{}(obj)
```

Gross? We'd probably resort to adding a non-member function - which currently doesn't exist in the standard library:

```cpp
template <typename T>
    requires requires sizeof(std::hash<T>)
size_t get_hash(T const& obj) {
    return std::hash<T>{}(obj);
}
```

It's not like this is hard to do. It's just that... we have to do it.

How would we implement `Eq` as a specialization? Well, you can't really. There's just <span class="token important">no associated functions</span> with this approach. We could declare a non-member `operator==`{:.language-cpp}... somewhere, but it wouldn't be in user types' associated namespaces - since now user types are totally unrelated to this class template `Eq`. For some concepts, we can still get value even without associated functions (like `Printable` or `std::hash`{:.language-cpp}) but for concepts like `Eq` it's a total nonstarter.

But implementing parameterized concepts is fine. `Range` translates well:

```cpp
template <typename T>
struct MyVec {
    T* begin_;
    T* end_;
    T* capacity_;
};

template <typename T>
struct Range<MyVec<T>> {
    static T* begin(MyVec<T>& v) { return v.begin_; }
    static T* end(MyVec<T>& v) { return v.end_; }
};

template <typename T>
struct Range<MyVec<T> const> {
    static T const* begin(MyVec<T> const& v) { return v.begin_; }
    static T const* end(MyVec<T> const& v) { return v.end_; }
};
```

And, as mentioned earlier, the unobtrusive nature of the specialization approach means we can opt-in for things like... arrays!

But again, we get no associated functions at all. Even something like providing an `iterator` type alias, that's something that every type opting in would have to do themselves (or have a separate trait to do so). We do get a single uniform syntax for traversal though: it's always `Range<T>::begin(r)`{:.language-cpp} and `Range<T>::end(r)`{:.language-cpp}.

### CRTP

There is a third approach that is a hybrid of the previous two: the Curious Recurring Template Pattern, or CRTP. Whereas specialization is not useful for `Eq` (where the primarily goal was to provide associated functions), CRTP is not super useful for `Printable` (where the primarily goal is to customize one function). But for `Eq`, it works quite nicely (and this is roughly how Boost.Operators works):

```cpp
template <typename Derived>
struct Eq {
  friend bool operator==(Derived const& lhs, Derived const& rhs) {
    return lhs.equals(rhs);
  }
    
  friend bool operator!=(Derived const& lhs, Derived const& rhs) {
    return !lhs.equals(rhs);
  }    
};

struct SeqNum : Eq<SeqNum>
{
private:
    friend Eq;
    bool equals(SeqNum const& rhs) const {
        return value == rhs.value;
    }
    int value;
};
```

Unlike with inheritance, I can't mark `equals()`{:.language-cpp} as `override`. Indeed, there's no real way for `Eq` to signal what exactly its interface is! While `SeqNum` <span class="token important">explicitly</span> must inherit from `Eq<SeqNum>`{:.language-cpp}, it must <span class="token important">implicitly</span> implement the interface. We do still have to inherit from `Eq<T>`{:.language-cpp}, so this is an <span class="token important">intrusive</span> approach - and given the implicit nature of the interface is inherently <span class="token important">checked late</span>.

But as demonstrated above, we can easily provide <span class="token important">associated functions</span> - which is one of the primary motivations for this particular design choice, and why libraries like `boost::iterator_facade`{:.language-cpp} are very useful.

### Member and non-member functions

The last major mechanism for customization in C++ today are simply: write functions. This is actually the mechanism we use today for the main concepts I've been talking about in this whole post. If I want to make my type printable, I just have to know what the appropriate function I have to implement (as opposed to the appropriate type to inherit from or template to specialize):

```cpp
struct SeqNum {
    int value;
};

std::ostream& operator<<(std::ostream& os, SeqNum const& s) {
    return os << "SeqNum(" << s.value << ")";
}
```

This particular one has to be a non-member, but others could be member functions as well - the choice is up to the type author:

```cpp
struct SeqNum {
    bool operator==(SeqNum const& rhs) const {
        return value == rhs.value;
    }
    bool operator!=(SeqNum const& rhs) const {
        return value == rhs.value;
    }
    int value;
};
```

This approach is <span class="token important">implicit</span> - nowhere am I naming the concept that I'm implementing with these functions. We just know that `ostream& operator<<(ostream&, T const&)`{:.language-cpp} is printing, and `operator==`{:.language-cpp} and `operator!=`{:.language-cpp} is for equality, and `begin()`{:.language-cpp} and `end()`{:.language-cpp} and `size()`{:.language-cpp} and `data()`{:.language-cpp} are for ranges.

The implicitness has consequences - you could unintentionally be opting into a concept you don't even know about. While this is _exceedingly_ unlikely for something like `Range` (where you need two functions that both need to return specific types that themselves have a lot of requirements), it could easily happen with less onerous concepts.

It's not totally outrageous to use the name `begin()`{:.language-cpp} to mean something that isn't an iterator. It's not absurd to use the name `data()`{:.language-cpp} to mean something other than returning a pointer to the beginning of a contiguous range. Those names are reserved in a way - which is kind of okay since it's the standard library and everyone knows them, but what about a concept that I might want to write in my own library? What if I pick a name that you're using for something else? Trouble... 

Because we typically have a choice - we can write member `begin()`{:.language-cpp} or non-member `begin()`{:.language-cpp} and we could even go wild and have a member `begin()`{:.language-cpp} with a non-member `end()`{:.language-cpp} - this is an <span class="token important">unobtrusive</span> customization mechanism. The member syntax gives users a much nicer ergonomic experience than the non-member syntax, so users might prefer to use those where possible. But the member syntax isn't always possible - you cannot add members to types you don't own, and you definitely cannot add members to things like the fundamental types or arrays. As a result, any generic program must be able to deal with both - which requires having non-member syntax that just defers to member syntax:

```cpp
namespace std {
  template <typename C>
  auto begin(C& c) -> decltype(c.begin()) { return c.begin(); }
}
```

and then using the [Two Step](http://ericniebler.com/2014/10/21/customization-point-design-in-c11-and-beyond/) consistently:

```cpp
template <typename R>
void some_algo(R&& range) {
  using std::begin, std::end;
  auto first = begin(range);
  auto last = end(range);
  for (; first != last; ++first) {
    // ...
  }
}
```

You won't find out if you properly customized your type for the concept until you use it - it's <span class="token important">checked late</span>. And concept checking is hard! You have to evaluate an arbitrary number of tests at point of use.

We also get <span class="token important">no associated functions</span> and the niceness of the syntax is variable - users that provide member function opt-in can use member functions, but the library cannot, and you can't add new functions that way either. There has been an enormous amount of effort in the language and library to give us better syntax for these cases. Consider:

- `operator`{:.language-cpp}s have special name lookup rules to allow for member or non-member declarations
- `<=>`{:.language-cpp} exists at least in part to provide a better opt-in experience for comparisons
- range-based `for`{:.language-cpp} statements hide the variability in how `begin()`{:.language-cpp} and `end()`{:.language-cpp} are declared
- the new CPOS -- like `std::ranges::begin()`{:.language-cpp} and `std::ranges::end()`{:.language-cpp} -- do the same on the library side and avoid needing the Two Step
- the range adapters give us the kind of... mostly associated functions we want with pretty good syntax

Even further consider:

- my [previous post]({% post_url 2019-04-13-ufcs-history %}) went through the history of language proposals in the space of a unified function call syntax, or UFCS. It is precisely these problems that those proposals tried to solve: the variability in type author choice for opting into concepts by "just" declaring functions and being able to do so using either member or non-member functions, and wanting to have nice syntax for associated functions. 
- an [earlier post]({% post_url 2018-10-20-concepts-declarations %}) went through the difficulties in constructing certain kinds of constrained declarations. These difficulties result form a lack of associated types.

### Inheritance, Specialization, CRTP, and Functions

To summarize the differences:

| Inheritance | Specialization | CRTP | Functions |
|-------|--------|---------|
| explicit | explicit | explicit | implicit |
| intrusive | unobtrusive | intrusive | user's choice |
| checked early | checked late | checked late | checked late |
| can provide associated functions/types | no associated functions | can provide associated functions/types | no associated functions |

<br />
If I could have anything I want, what would I actually want out of here?

- I'd want an <span class="token important">explicit</span> opt-in mechanism. In all of these cases, I'm explicitly opting into a particular concept when I write the code anyway. I don't see much value in being able to omit that. It also makes the intent clear, and makes it impossible to accidentally opt into someone else's concept.
- I'd absolutely require an <span class="token important">unobtrusive</span> opt-in mechanism. It's essential to be able to implement support for various concepts for fundamental types or for types you don't own. 
- I'd want my opt-in to be <span class="token important">checked early</span>. Of course, the earlier I catch my mistakes the better. 
- I'd want to be able to <span class="token important">provide associated functions and types</span>. Both because it provides the maximal benefit of customization and because it can provide a good ergonomic story for users.

As you can see in the table above, we have no such thing in the language today. But maybe that's the direction we should be considering. Several languages provide something that fits those boxes: Rust traits, Swift protocols, Haskell type classes. And C++0x concepts did as well. 