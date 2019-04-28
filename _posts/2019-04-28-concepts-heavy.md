---
layout: post
title: "Concepts Heavy"
category: c++
tags:
 - c++
 - concepts
series: concepts-2
pubdraft: yes
--- 

The previous post described the several ways we have today of writing customizable interfaces: polymorphism with `virtual`{:.language-cpp} functions, class template specialization, CRTP, and "well-known" member or non-member functions. They each have their advantages and disadvantages. And really, sometimes simple polymorphism is very much the best solution. But there's a hole in our design space that suggests that we need something more. 

A lack of associated types leads to a proliferation of type traits. Consider a concept like `Invocable<F, Args...>`{:.language-cpp}. All it tells us is whether or not `f(args...)`{:.language-cpp} is valid - it doesn't tell us what type that expression has. While sometimes we don't care (`std::for_each()`{:.language-cpp} doesn't), most of the time we do - and to find that answer out we need to use `invoke_result_t<F, Args...>`{:.language-cpp}. Likewise, `Range<R>`{:.language-cpp}. What is the underlying iterator for the range? `iterator_t<R>`{:.language-cpp}. Underlying value type? `value_type_t<iterator_t<R>>`{:.language-cpp}. And so forth. 

A lack of core customization mechanism leads to the "Two Step":

```cpp
r.begin(); // wrong
begin(r);  // wrong
std::begin(r); // wrong

using std::begin;
begin(r); // correct
```

This problem was the motiviation for what I called the CS1 direction of [UFCS]({% post_url 2019-04-13-ufcs-history %}) (having `f(x, y)`{:.language-cpp} find `x.f(y)`{:.language-cpp}). It's also a motivation for Matt Calabrese's [P1292](https://wg21.link/p1292). Ranges' solution to this problem was to introduce _customization point objects_:

```cpp
std::ranges::begin(r); // correct
using namespace std::ranges;
begin(r); // also correct

auto f = std::ranges::begin;
f(r); // also correct
```

CPOs are, in my opinion, quite the library engineering feat. They're an impressive solution to this problem today - but they're quite subtly difficult to implement and require a lot of work.

A lack of associated functions leads to the proposed CS2 direction of UFCS (having `x.f(y)`{:.language-cpp} find `f(x, y)`{:.language-cpp}) and similar proposals in that space for extension functions. Ranges solved this in library with the pipeable adapters: `x | f(y)`{:.language-cpp} is fairly close visually to `x.f(y)`{:.language-cpp}, and the pipeable adapters are substantially easier to write than CPOs (although still some boilerplate).

It's these lacks that I think can and should be addressed with better `concept`{:.language-cpp}s. [Concepts Lite](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2013/n3580.pdf) was the proposal that eventually became C++20 concepts. It was, by design, a lighter weight version of "C++0x Concepts". I think we can incrementally plug them in to get a more complete generic concept mechanism in C++. Here's a sketch of what I'm thinking.


### `Invocable`{:.language-cpp}

Let's start with [`Invocable`](http://eel.is/c++draft/concept.invocable), which in C++20 is specified as:

```cpp
template<class F, class... Args>
  concept Invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...);
  };
```

As mentioned earlier, this tells me _if_ I can invoke something but not what I get out of it. As a result, any closely-related `concept`{:.language-cpp}s have to just know about its related type traits (effectively, instead of directly associated types we have well-known associated type traits?). For instance, a [`Predicate`{:.language-cpp}](http://eel.is/c++draft/concept.predicate) is an `Invocable`{:.language-cpp} that returns `bool`{:.language-cpp}:

```cpp
template<class F, class... Args>
  concept Predicate = RegularInvocable<F, Args...> &&
    Boolean<invoke_result_t<F, Args...>>;
```

It would be nice if these types were more closely associated. Let's start with a new way of declaring concepts that look more like `struct`{:.language-cpp}s:

```cpp
template <typename F, typename... Args>
concept struct Invocable2 {
    typename result_type;
    virtual result_type operator()(F&&, Args&&...);
};
```

This new kind of `concept`{:.language-cpp} is based on "pseudo-signatures" rather than expressions, and the significance of this will become more apparent later. But for now, this concept is satisfied if each `virtual`{:.language-cpp} function declaration here is satisfied... in this case meaning that `declval<F&&>()(declval<Args&&>()...)`{:.language-cpp} is well-formed. The result of that expression is stored in the type alias `result_type`. As presented above, `Invocable2` is an incomplete solution to `Invocable` - it is not currently satisfied by pointers to members (not for my lack of trying). I'll get into how to fix that later.

The advantage to this declaration, so far, is that we can write:

```cpp
template<class F, class... Args>
  concept Predicate2 = RegularInvocable<F, Args...> &&
    Boolean<Invocable2<F, Args...>::result_type>;
```

This isn't _shorter_ than the initial version - but it reduces the surface area of things you have to know in order to be able to write and use concepts. And that's a win. But don't worry, I'll get to shorter as well. We also don't need `typename`{:.language-cpp} here - it's deliberately not `typename Invocable2<F, Args...>::type`{:.language-cpp}. This is because `concept`{:.language-cpp}s cannot be specialized, so we know that `::result_type`{:.language-cpp} will always exist and be a type.

### `swap(a, b)`{:.language-cpp}

The next, more complicated example, is really the motivating example for the need for the "Two-Step" and the motivating example in P1292: `swap`{:.language-cpp}. How do we allow for customizing swap while still making it easy to check and use? In this sketch:

```cpp
template <typename value T>
concept struct Swap {
    virtual void swap(T& a, T& b) noexcept(/* ... */)
    {
        T tmp(std::move(a));
        a = std::move(b);
        b = std::move(tmp);
    }
};
```

A few new things here. `typename value T`{:.language-cpp} is just sugar to indicate that this type's value category is unimportant. Effectively this is doing `remove_reference_t<T>`{:.language-cpp} implicitly everywhere for convenience. That is, `Swap<int&>`{:.language-cpp} means the same thing as `Swap<int>`{:.language-cpp}.

Here also we have a `virtual`{:.language-cpp} function body in addition to just the declaration. `Swap<T>`{:.language-cpp} is implicitly satisfied as a concept if I can, for each `virtual`{:.language} function `F`:

- find a preexisting match for `F` for the given type, or
- if `F` has a body, instantiate the body

The "preexisting match" algorithm is similar to what the CPOs do today. In this case, we would look for:

1. A member function. If `declval<T&>().swap(declval<T&>())`{:.language-cpp} is valid, then we're satisfied.
2. A non-member function. If argument-dependent lookup (only) can find a `swap(declval<T&>(), declval<T&>())`{:.language-cpp} that would be selected in the presence of a poisoned `swap(U&, U&)`{:.language-cpp} overload, then we're satisfied.

Some examples to help explain how this works:

```cpp
// valid because we don't have any more specific matches, so we
// instantiate the body and that's valid for T=int
static_assert(Swap<int>);

// invalid because we don't have any more specific matches, and
// instantiating the body fails because std::mutex isn't movable
static_assert(!Swap<std::mutex>);

namespace N {
    template <typename U> void swap(U&, U&);
    struct X {
        X(X&&) = delete;
    };
    
    struct Y {
        Y(Y&&) = delete;
        void swap(Y&);
    };
    
    struct Z {
        Z(Z&&) = delete;
        friend void swap(Z&, Z&);
    };
}

// invalid because N::swap doesn't count for meeting the
// non-member requirements, and instantiating the body of
// Swap::swap fails because X isn't movable
static_assert(!Swap<X>);

// valid, because we find Y::swap. Doesn't matter that Y isn't
// movable
static_assert(Swap<Y>);

// valid, because we find the non-member swap(Z&, Z&), which
// satisfies the requirements. Doesn't matter that Z isn't movable
static_assert(Swap<Z>);
```

Of course, simplifying knowing _if_ a type is swappable isn't interesting at all. We need to also be able to actually swap it. And this is where the fact that we use "pseudo-signatures" comes in handy. They're not actually pseudo - they're full signatures. We can invoke them - and the invocation goes through the same lookup process described above:

```cpp
// Swap<int> is satisfied by the default implementation, so this
// goes through that
int i1, i2;
Swap<int>::swap(i1, i2); 

// Swap<Y> is satisfied by the member function Y::swap, so this
// is the same as y1.swap(y2)
N::Y y1, y2;
Swap<Y>::swap(y1, y2);

// Likewise this is swap(z1, z2)
N::Z z1, z2;
Swap<Z>::swap(z1, z2);
```

Of course, explicitly specifying the template arguments is so passé. We have CTAD, and the same deduction rules should be able to be applied here:

```cpp
Swap::swap(i1, i2); // Swap<int>
Swap::swap(y1, y2); // Swap<Y>
```

And, moreover, we don't want these to be actual functions. There are numerous benefits to these being objects - so these should behave as objects as well - in a way that follows from use:

```cpp
// this is an object with an operator()(int&, int&)
auto swap_i = Swap<int>::swap;
swap_i(i1, i2); // ok
swap_i(y1, y2); // error

// this is an object with effectively
// template <Swap T>
// operator()(T&, T&)
auto f = Swap::swap;
f(i1, i2); // ok
f(y1, y2); // ok
```

One such benefit from allowing these to behave like objects? We can provide an easy alias:

```cpp
// Here's my concept
template <typename value T>
concept struct Swap {
    virtual void swap(T& a, T& b) noexcept(/* ... */)
    {
        T tmp(std::move(a));
        a = std::move(b);
        b = std::move(tmp);
    }
};

// ... and here's my CPO
inline constexpr auto swap = Swap::swap;
```

### Opting into `Swap`{:.language-cpp}

Let's say I have some simplified version of `std::unique_ptr`{:.language-cpp}

```cpp
template <typename T>
class my_unique_ptr {
    T* ptr = nullptr;;
public:
    my_unique_ptr();
    explicit my_unique_ptr(T*);
    my_unique_ptr(my_unique_ptr&&) noexcept;
    my_unique_ptr& operator=(my_unique_ptr&&) noexcept;
    ~my_unique_ptr();
};
```

It's already the case that `Swap<my_unique_ptr<T>>`{:.language-cpp} for all `T`, since this type is move-constructible and move-assignable. But we can swap more efficiently than that. So how do we provide a more efficient opt-in? We have several options.

The familiar mechanism relies upon the implicit lookup rules described above. We can either add a member function or a non-member function that is more specific than a catch-all template:

```cpp
template <typename T>
class my_unique_ptr {
public:
    // member version
    void swap(my_unique_ptr& rhs) {
        Swap::swap(ptr, rhs.ptr);
    }
    
    // non-member version
    friend void swap(my_unique_ptr& lhs, my_unique_ptr& rhs) {
        Swap::swap(lhs.ptr, rhs.ptr);
    }
}
```

But I'd like to be able to be more explicit than that. [N1758](https://wg21.link/n1758) talks about the difference between _named conformance_ and _structural conformance_. The above approach relies on structural conformance - we match the structure, therefore we match. This effectively leads to a land-grab of names. 

Instead, we could opt-in through named conformance - that is, our opt-in explicitly names the concept `Swap`. This has some advantages. The whole point of writing a `swap` function is so that `Swap::swap`{:.language-cpp} (or, in Ranges, `std::ranges::swap`{:.language-cpp}) can use it - so the added explicitness doesn't hurt. We no longer have to rely on ADL, and we no longer have to worry about having larger overload sets than necessary. These opt-ins are _only_ found when invoking a concept's functions.

```cpp
template <typename T>
class my_unique_ptr {
    friend concept Swap;
    // ..
};

template <typename T>
concept Swap<my_unique_ptr<T>> {
    void swap(my_unique_ptr<T>& lhs,
              my_unique_ptr<T>& rhs)
    {
        Swap::swap(lhs.ptr, rhs.ptr);
    }
};
```

Within explicit models, you must provide an implementation of every `virtual`{:.language-cpp} function in a concept, and each such implementation will be checked to ensure that it matches the base signature. Had we written `swap` to take 3 arguments or 1, that's an error at point of definition.

We can also do this kind of explicit modelling internal to the type:

```cpp
template <typename T>
class my_unique_ptr {
    concept Swap {
        void swap(my_unique_ptr& lhs, my_unique_ptr& rhs) {
            Swap::swap(lhs.ptr, rhs.ptr);
        }
    };
};
```

or by explicitly annotating functions as being `override`s:

```cpp
template <typename T>
class my_unique_ptr {
public:
    void my_swap(my_unique_ptr& rhs) override(Swap::swap) {
        Swap::swap(ptr, rhs.ptr);
    }
};
```

The `override` keyword will enforce, at point of definition, that this signature matches.

### A terser syntax

Let's go back to one of my [favorite examples]({% post_url 2018-10-20-concepts-declarations %}): `fmap()`{:.language-cpp}. With this new kind of concept that allows for associated types, we could write the following declaration and implementation:

```cpp
template <typename T, Invocable<T> F,
    typename U = Invocable<F, T>::result_type>
vector<U> fmap(F f, vector<T> ts)
{
    vector<U> us;
    us.reserve(ts.size());
    for (auto&& t : ts) {
        us.push_back(f(t));
    }
    return us;
}
```

So far, we're only a little bit better than C++20 in that we can use `Invocable<F, T>::result_type`{:.language-cpp} instead of `invoke_result_t<F, T>`{:.language-cpp}. But this implementation is actually wrong for a few reasons:

1. `Invocable<F, T>`{:.language-cpp} does not mean that I can write `f(t)`{:.language-cpp}, it means I can write `invoke(f, t)`{:.language-cpp}
2. And even that is wrong, because it actually means we can write `invoke(move(f), move(t))`{:.language-cpp}
3. ... And there's really no guarantee that `t` is actually a `T` anyway (thanks, `vector<bool>`{:.language-cpp}). If it's not, we could be doing something outside of our constraint that may or may not work.

Taking a step back, one of the examples that appeared in multiple concepts papers in the 2000s was the following:

```cpp
// equivalent using C++20 syntax
template <typename T>
concept LessThanComparable = requires(T const a, T const b) {
    { a < b } -> bool;
};

template <LessThanComparable T>
bool foo(T x, T y) {
    return x < y && random() % 3;
}
```

Now consider a type like:

```cpp
struct Evil {
    explicit operator bool() const;
    void operator&&(int);
    
    Evil operator<(Evil) const;
};
```

It's bullshit like this that led to the incredible complexity of the [`Boolean` concept](http://eel.is/c++draft/concept.boolean). But rather than rely on every library author to get this right, maybe we can lean on the language to help you out. C++0x concepts did this implicitly, but maybe it's enough to do so explicitly with the help of a new access operator which I will spell `..`:

```cpp
template <typename F, typename... Args>
concept LvalueInvocable : Invocable<F&, Args...>
{ };

template <typename T, LvalueInvocable<T const&> F,
    typename U = F..result_type> // (*)
vector<U> fmap(F f, vector<T> ts)
{
    vector<U> us;
    us.reserve(ts.size());
    for (auto&& t : ts) {
        us.push_back(f..(t)); // (*)
    }
    return us;
}
```

The main change here is on the two marked lines. What `..` means will actually differ between dependent and non-dependent contexts. Within a dependent context, we will look for the name on the right-hand-side only inside of those concepts that the left-hand side is constrained on. Outside of dependent contexts, we will look in any concept that we can find that matches. So in here, `F` is constrained on `LvalueInvocable<T>`{:.language-cpp}, which has a `result_type` typename and a function named `operator()`{:.language-cpp}.

Both of those accesses are syntax sugar for the full rewrites using the concept name. `F..result_type` becomes `LvalueInvocable<F, T>::result_type`{:.language-cpp} and `f..(t)`{:.language-cpp} becomes `LvalueInvocable<F, T>::operator()(f, t)`{:.language-cpp} - the latter of which is a specific signature that takes an `F&&`{:.language-cpp} and a `T&&`{:.language-cpp} and, by construction, definitely returns a `U`. This rewrite is pretty significant for generic code - it ensures that we are definitely doing the thing that we think we're doing!

Even nicer, is we could condense the declaration somewhat:

```cpp
template <typename T, typename U,
    LvalueInvocable<T const&, ..result_type=U> F>
vector<U> fmap(F, vector<T>);
```

Which doesn't seem like it matters to much until we try to implement monadic bind:

```cpp
template <typename T, typename U,
    LvalueInvocable<T const&, ..result_type=vector<U>> F>
vector<U> bind(F, vector<T>);
```

Or the final boss of that blog post - implementing `sequence()`{:.language-cpp} over a `Range` of `expected<T, E>`{:.language-cpp}:

```cpp
template <typename T, typename E,
    Range<..value_type = expected<T, E>> R>
expected<vector<T>, E> sequence(R&&);
```

Cool.

### Ranges and things

Ranges is the one significant library that uses C++20 concepts, so far. And it's a great model of whether a new concepts design could be better for library authors and library users. There's a few things that Ranges does that, at least to me, seem like workarounds for concepts limitations. One such limitation is that concepts are always implicit. But take something like `View` - that's a purely semantic distinction from `Range` and thus makes sense (at least to me) to be an `explicit`{:.language-cpp} opt-in:

```cpp
template <typename value R>
concept struct Range {
    typename Iterator iterator;
    typename Sentinel<Iterator> sentinel;
    typename value_type = iterator..value_type;
    // ... other useful aliases ... 
    
    iterator begin(R&);
    sentinel end(R&);
};

inline constexpr auto begin = Range::begin;
inline constexpr auto end = Range::end;

template <typename value V>
explicit concept struct View : Range<V> { };
```

In this definition, `vector<int>`{:.language-cpp} implicitly models `Range` by the rules I've laid out above, but it doesn't model `View` because it doesn't explicitly do so. The above doesn't quite perfectly fit into C++20 Ranges because there's a special case of what it means to call `begin` on an rvalue, but this is still in early exploration stages. The added associated types here mean that I can write something like:

```cpp
template <std::ranges::Range R>
void foo(R&& rng) {
    R..iterator it = rng..begin();
}
```
instead of:
```cpp
template <std::ranges::Range R>
void foo(R&& rng) {
    std::ranges::iterator_t<R> = std::ranges::begin(rng);
}
```

Realistically, most people would use `auto`{:.language-cpp} there anyway but it's nice to know that there's a nice way to name types if we want to name them.

The more interesting usage here for me is to talk about the adapters. The adapters in Ranges are driven in large part off of the concept [`ViewableRange`](http://eel.is/c++draft/range.refinements):

```cpp
template<class T>
  concept ViewableRange =
    Range<T> && (forwarding-range<T> || View<decay_t<T>>);
```

which in this design would look more like:

```cpp
// A ViewableRange is something that can be converted to a View
// safely. Note that a ViewableRange isn't necessarily a Range
// in this design. It's anything that can give you a view.
template <typename T>
explicit concept ViewableRange
{
    typename View view_type;
    virtual view_type view(T&&);
};

// ... which is what all_view does:
inline constexpr auto all = ViewableRange::view;

// lvalue ranges can be safely converted to a View
template <Range R>
concept ViewableRange<R&> {
    auto view(R& range) {
        return ref_view{range};
    }
};

// Views can, obviously, be safely converted to a View
template <View V>
concept ViewableRange<V&> {
    auto view(V v) { return v; }
};

template <typename V>
    requires View<remove_const_t<V>>
concept ViewableRange<V&&> {
    auto view(V v) { return v; }
};
```

This design completely restructures how we approach writing range adapters. In C++20, adapters like `filter` and `transform` require a `ViewableRange` and then implement the appropriate machinery to get that to work, along with separate appropriate machinery to get `|` to work. The design is that `rng | view::filter(f)`{:.language-cpp} means the same thing as `view::filter(rng, f)`{:.language-cpp} which means the same thing as `filter_view{rng, f}`{:.language-cpp}. We can actually just stick all of that into the `ViewableRange` concept:

```cpp
template <typename T>
explicit concept ViewableRange
{
    typename View view_type;
    typename value_type = view_type..value_type;
    typename reference = view_type..reference;
    // ... some other aliases
    
    // the one function that needs to be implemented to satisfy
    // this concept.
    virtual view_type view(T&&);
    
    // these are NOT virtual - they are associated functions and
    // are always available
    View auto filter(T&& rng, Predicate<reference> auto&& pred) {
        // explicitly satisfy View here
        struct filter_view : View  
        {
            // ...
        };
        return filter_view{FWD(rng)..view(), FWD(pred)};
    }
    
    View auto transform(T&& rng,
        LvalueInvocable<reference> auto&& f)
    {
        // note that I can use f..result_type here
        struct transform_view : View
        {
            // ...
        }
        return transform_view{FWD(rng)..view(), FWD(f)};
    }
    
    // lots more adapters here...
};
```

All these adapters don't _have_ to live inside of `ViewableRange`. Users can extend this to write their own:

```cpp
template <typename VR>
concept struct Accumulate : ViewableRange<VR>
{
    template <typename U,
        LvalueInvocable<U&&, VR..reference> F = std::plus>
            requires ConvertibleTo<F..result_type, U>
    U accumulate(VR&& rng, U init, F op = {})
    {
        for (auto&& elem : FWD(rng)..all()) {
            init = op..(std::move(init), elem);
        }
        return init;
    }
};
```

The culmination of all of this effort is that we can write:

```cpp
bool is_even(int i) { return i % 2 == 0; }
std::vector<int> ints = {1, 2, 3, 4, 5, 6};

auto sum = ints..filter(is_even)
               ..transform([](int x){ return x * x; })
               ..accumulate(0);
assert(sum == 56);
```

This works because `ints` is an lvalue of type `vector<int>`{:.language-cpp}, which implicitly models `Range` by having member `begin()`{:.language-cpp} and `end()`{:.language-cpp} which satisfy the other requirements as well (all of which are checked of course). Lvalues which satisfy `Range` explicitly model `ViewableRange`. So `ints` can find the associated function `filter` through that concept. Whatever the result of `ints..filter(is_even)`{:.language-cpp} is models `View`, and all `View`s are `ViewableRange`s so again `transform` is an associated function of that. And lastly we find `accumulate` by way of the implicitly satisfied concept `Accumulate`.

I, for one, think this is a pretty cool place to end up.

### Tuple-like and Variant-like

One of the places where we don't have concepts today that would be interesting to try to apply them would be the tuple-like concept (used by structured bindings) and the variant-like concept (eventually used by pattern matching). These are actually difficult to describe, but a rough sketch might be as follows.

```cpp
template <typename value T>
explicit concept TupleLike {
    virtual constexpr size_t size;
    
    template <size_t I> requires (I < size)
    virtual typename element_type;
    
    template <size_t I> requires (I < size)
    virtual element_type<I>& get(T&);
    
    template <size_t I> requires (I < size)
    virtual element_type<I>&& get(T&& t) {
        if constexpr (is_lvalue_reference_v<element_type<I>>) {
            return get(t);
        } else {
            return std::move(get(t));
        }
    }
};
```

How does `static_assert(TupleLike<X>)`{:.language-cpp} check that `get` and `element_type` work for all the right `I`s? Not sure.

`std::tuple`{:.language-cpp} would opt into via:

```cpp
template <typename... Ts>
concept TupleLike<std::tuple<Ts...>> {
    constexpr size_t size = sizeof...(Ts);
    
    template <size_t I>
    using element_type = std::tuple_element_t<
        I, std::tuple<Ts...>>;
    
    template <size_t I>
    decltype(auto) get(std::tuple<Ts...>& t) {
        return std::get<I>(t);
    }
    
    // don't need to provide the rvalue reference overload
    // the default does the right thing for us
};

// similar for std::tuple<Ts...> const
```

### Summary

In short, this design gives us a full customization system, with named conformance instead of structural conformance. It allows us to directly and easily opt-in to interfaces implicitly or explicitly, and use first class syntax in generic algorithms regardless of how the user chooses to opt-in (the "CS1" part of UFCS).

It gives us a new access syntax (`..`) that both provides syntax sugar to ensure that generic algorithms are using the constraints they say they want so that they're doing what they think they're doing, and gives us nice syntax for extension methods (the "CS2" part of UFCS). 

It also gives us CPOs for free and obviates the need for arbitrary type traits.