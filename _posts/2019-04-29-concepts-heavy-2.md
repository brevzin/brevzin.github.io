---
layout: post
title: "Concepts Heavy (2)"
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

For those libraries whose customization is based on class template specialization, a lack of a nice language mechanism to actually _use_ this customization leads to further library additions - like [P0549](https://wg21.link/p0549)'s `std::hash_value()`{:.language-cpp}.

A lack of associated functions leads to the proposed CS2 direction of UFCS (having `x.f(y)`{:.language-cpp} find `f(x, y)`{:.language-cpp}) and similar proposals in that space for extension functions. Ranges solved this in library with the pipeable adapters: `x | f(y)`{:.language-cpp} is fairly close visually to `x.f(y)`{:.language-cpp}, and the pipeable adapters are substantially easier to write than CPOs (although still some boilerplate).

It's these lacks that I think can and should be addressed with better `concept`{:.language-cpp}s. [Concepts Lite](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2013/n3580.pdf) was the proposal that eventually became C++20 concepts. It was, by design, a lighter weight version of "C++0x Concepts". I think we can incrementally plug them in to get a more complete generic concept mechanism in C++. Here's a sketch of what I'm thinking.

### `Drawable`{:.language-cpp}

Let's start with a basic concept to introduce a bunch of new ideas:

```cpp
template <typename T>
concept struct Drawable {
    virtual void draw(T const&, std::ostream&);
};
```

This new kind of `concept`{:.language-cpp} is based on "pseudo-signatures" rather than expressions, and these pseudo-signatures can even be `virtual`{:.language-cpp}! But this is a slightly different `virtual`{:.language-cpp} than we're used to, although it's a remarkably good analogue (copped from Matt Calabrese's [P1292](https://wg21.link/p1292)). What we mean is that any type which satisfies `Drawable` will satisfy, and can override, the function `draw`. Later, we'll see examples of non-`virtual`{:.language-cpp} functions inside of `concept`{:.language-cpp}s - those cannot be overriden. However, unlike regular polymorphism, here we determine the correct override statically at compile time rather than at runtime through the use of a vtable. There is no overhead at runtime - it's basically overload resolution. This is static polymorphism, not dynamic polymorphism.

A type can satisfy `Drawable` either implicitly or explicitly. There are two ways implicit satisfaction can happen: via a member function or via a non member function.

We can have a member function named `draw` that can be invoked on a `T const&`{:.language-cpp} that can take a `std::ostream&`{:.language-cpp} and return something compatible with `void`{:.language-cpp} (which is to say, any or no return is fine). For example:

```cpp
struct Square {
    void draw(std::ostream& os) const { os << "Square"; }
};
static_assert(Drawable<Square>);

struct BadSquare {
    void draw() const { std::cout << "BadSquare"; }
};
static_assert(!Drawable<Square>);
```

Or we can have a non-member function which is found by argument-dependent lookup (only) and is likewise compatible with the signature:

```cpp
struct Circle {
    friend void draw(Circle c, std::ostream& os) {
        os << "Circle";
    }
};
static_assert(Drawable<Circle>);

template <typename T>
void draw(T&&, std::ostream&);
namespace N {
    struct BadCircle { };
    // there may be a ::draw, but it's not found by ADL
    static_assert(!Drawable<BadCircle>);
}
```

... with the added caveat that ADL must find a better match than the signature itself. In other words, it's as if the lookup happens in a context that includes the poison pill:

```cpp
template <typename T>
void draw(T const&, std::ostream&) = delete;
```

so as to exclude potentially accidental matches:

```cpp
namespace M {
    // is this really the same thing? I dunno...
    template <typename... Ts>
    void draw(Ts&&...);
    
    struct BadPentagon{ };
}

// match isn't good enough
static_assert(!Drawable<M::BadPentagon>);
```

So far, this is similar to how we can have member or non-member `begin()`{:.language-cpp} to model `Range`. But in addition to these two methods, we can also explicitly satisfy the concept by syntax similar to template specialization. This idea is known as a concept map:

```cpp
struct Triangle { };
template <>
concept Drawable<Triangle> {
    void draw(Triangle const&, std::ostream& os) {
        os << "Triangle";
    }
};
static_assert(Drawable<Triangle>);

struct BadTriangle { };
template <>
concept Drawable<BadTriangle> {
    // compile error here: draw is incompatible with the
    // declaration in the concept
    void draw(std::ostream& os, BadTriangle) {
        os << "BadTriangle";
    }
}
```

Here is one advantage already - because we are explicitly opting into `Drawable` (which arguably we were in the other cases as well), we can get the compiler to help us out and tell us we did something wrong (in this case, get the arguments in the wrong order) at the point that we got it wrong - rather than sometime later. In other words, early checking rather than late checking.

We can also get this help through implicit satisfcation:

```cpp
struct Oval
    : Drawable // I intend to satisfy Drawable
{
    // okay, good, I succeeded in satisfying Drawable
    void draw(std::ostream&) const;
};

struct BadOval : Drawable
{ }; // error: !Drawable<BadOval>
```

This last bit is just syntax sugar for having written the `static_assert` yourself, but sometimes having that early reminder can't hurt. We may also want to satisfy the model within the class itself (maybe we want to access some private member sor something):

```cpp
struct Squiggle
{
private:
    std::string name;
    
    template <>
    concept ::Drawable<Squiggle> {
        void draw(Squiggle const& s, std::ostream& os) {
            os << "Squiggle named " << s.name;
        }
    };
};
static_assert(Drawable<Squiggle>);
```

### Using `Drawable`{:.language-cpp}

Alright, so we have a new concept and we have three different ways of opting into it: `Square` had a member function, `Circle` had a non-member `friend`{:.language-cpp}, and `Triangle` and `Squiggle` did so explicitly. How do we actually use the thing? We clearly cannot do:

```cpp
template <Drawable T>
void draw_me(T const& shape) {
    shape.draw(std::cout);
}

draw_me(Square{});   // ok, prints Square
draw_me(Circle{});   // error
draw_me(Triangle{}); // error
```

Here's where the pseudo-signatures come in handy. Not only do these signatures help determine whether a concept is satisfied or not, they can also be invoked like an actual function. That is:

```cpp
// ok, prints Square. Exactly equivalent to having directly
// called the member function ourselves. No extra indirection
Drawable<Square>::draw(Square{}, std::cout);

// ok, prints Circle . Exactly equivalent to having directly
// called the non-member function ourselves. No extra indirection
Drawable<Circle>::draw(Circle{}, std::cout);

// ok, prints Triangle. Exactly equivalent to having directly
/// called the specialized function ourselves. No extra indirection
Drawable<Triangle>::draw(Triangle{}, std::cout);
```

Of course, explicitly specifying the template arguments is so passé. We have CTAD, and the same deduction rules should be able to be applied here:

```cpp
// ok, prints Square
Drawable::draw(Square{}, std::cout);

// ok, prints Circle
Drawable::draw(Circle{}, std::cout);

// ok, prints Triangle
Drawable::draw(Triangle{}, std::cout);
```

And, these should behave like objects as well. Referring to a particular specialization of a concept gives you a specialized call operator, whereas referring to the full concept gives you a constrained call operator template:

```cpp
// this is an object with a
// void operator()(Square const&, ostream&) const;
auto draw_sq = Drawable<Square>::draw;

draw_sq(Square{}, std::cout); // ok
// error, Circle not convertible to Square
draw_sq(Circle{}, std::cout); 

// this is an object effectively with a
// template <Drawable T>
// void operator()(T const&, std::ostream&) const;
auto draw = Drawable::draw;
draw(Square{}, std::cout); // ok
draw(Circle{}, std::cout); // ok
// error, BadSquare doesn't satisfy Drawable
draw(BadSquare{}, std::cout);

// ill-formed, BadSquare doesn't satisfy Drawable
auto draw_bad = Drawable<BadSquare>::draw;
```

One obvious way to use this feature is to just alias the concept's function:

```cpp
// Here's my concept
template <typename T>
concept struct Drawable {
    virtual void draw(T const&, std::ostream&);
};

// ... and here's my CPO
inline constexpr auto draw = Drawable::draw;
```

That's a ton of functionality in five lines of code.

### `swap(a, b)`{:.language-cpp}

Now let's consider the poster-child for all things dealing with customization, the motivating example for the need for the "Two-Step" and unsurprisingly the first example used in [P1292](https://wg21.link/p1292): `swap`{:.language-cpp}. How do we allow for customizing swap while still making it easy to check and use? In this sketch:

```cpp
template <typename T>
concept struct Swap {
    virtual void swap(T& a, T& b) noexcept(/* ... */)
    {
        T tmp(std::move(a));
        a = std::move(b);
        b = std::move(tmp);
    }
};

// CPO as before
inline contexpr auto swap = Swap::swap;
```

Whereas in the `Drawable` concept we just had a single virtual function declaration that had no definition, here we have one with a definition. What does that mean? The definition here provides a default implementation - it is effectively a third way to implicitly satisfy the concept. In this case, a type `T` is said to model `Swap` if (in order):

1. `T` explicitly models `Swap`
2. `T` has a member function, such that `declval<T&>().swap(declval<T&>())`{:.language-cpp} is a valid expression
3. ADL can find a non-member `swap` with the poison pill overload such that `swap(declval<T&>(), declval<T&>())` is a valid expression
4. If none of the above, we can instantiate the default definition without error

Only if we get to (4) do we try to instantiate the body. Some examples to help explain how this works:

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

### Coercing return types

Both of the concepts presented so far just had a single function which returned `void`{:.language-cpp}, and all of the models I showed did the same. But what happens if a model is a little bit more adventurous?

```cpp
template <typename T>
concept struct Drawable {
    virtual void draw(T const&, std::ostream&)
};

struct X {
    int draw(std::ostream&) const {
        return 42;
    }
};

static_assert(Drawable<X>);
```

The type `X` here does satisfy `Drawable`, even if a little oddly. And note that it returns `int`{:.language-cpp}. When using the concept signatures directly, this deviation is immaterial: we _always_ get the behavior dictated by the signature:

```cpp
// error: can't do void + int
Drawable::draw(X{}, std::cout) + 42; 
```

One of the examples that appeared many, many times in concepts papers in the early 2000s was the following (adjusted to C++20 syntax):

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

It's bullshit like this that led to the incredible complexity of the [`Boolean` concept](http://eel.is/c++draft/concept.boolean). But rather than rely on every library author to get this right, maybe we can lean on the language to help you out. Explicitly using the concept pseudosignature objects ensures that the code we are writing is doing the thing that we thing it is doing because we're ensuring, by construction, that it adheres to the interface. Let's make all the paranoiac casting a thing of the past.

### `f(x)`{:.language-cpp}

In C++20, the [`Invocable`](http://eel.is/c++draft/concept.invocable) concept is specified as:

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

It would be nice if these types were more closely associated. To that end, concept structs can declare types as well as functions:

```cpp
template <typename F, typename... Args>
concept struct Invocable2 {
    typename result_type;
    virtual result_type operator()(F&&, Args&&...);
};
```

What's new here is that rather than providing a return type for `operator()`{:.language-cpp}, we're just giving it a name. It's going to be determined by whatever `F(Args...)`{:.language-cpp} actually produces as an invocation result. `operator()`{:.language-cpp} is a little different than the earlier examples in that you cannot actually have a non-member `operator()`{:.language-cpp}, but you can have surrogate call operators.

Now, this definition isn't quite complete - it is not currently satisfied by pointers to members (not for my lack of trying) but those can be explicitly opted into. 

The advantage to this declaration, so far, is that we can write:

```cpp
template<class F, class... Args>
  concept Predicate2 = RegularInvocable<F, Args...> &&
    Boolean<Invocable2<F, Args...>::result_type>;
```

This isn't _shorter_ than the initial version - but it reduces the surface area of things you have to know in order to be able to write and use concepts. And that's a win. But don't worry, I'll get to shorter as well. We also don't need `typename`{:.language-cpp} here - it's deliberately not `typename Invocable2<F, Args...>::type`{:.language-cpp}. This is because `concept`{:.language-cpp}s cannot be specialized, so we know that `::result_type`{:.language-cpp} will always exist and be a type. Down with `typename`{:.language-cpp}!

### A terser syntax

Let's go back to one of my [favorite examples]({% post_url 2018-10-20-concepts-declarations %}): `fmap()`{:.language-cpp}. With this new kind of concept that allows for associated types, we could write the following declaration and implementation (`Invocable` here refers to the new-style `Invocable`, the one that has an associated type):

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

We can't catch those errors today until we test this with varying degrees of evil types. We'll probably find (2) pretty quickly and realize we used the wrong concept, but (1) could take a while if we don't think to use pointers to members. So let's at least fix (1) and (2):

```cpp
// same as your friend, C++17 std::invoke
inline constexpr auto invoke = Invocable::operator();

// this concept adds no extra requirements on top of Invocable
// it's just doing F& instead of F, so any type that models
// Invocable<F&, Args...> (implicitly or explicitly) will
// implicitly model LvalueInvocable<F, Args...> for free
template <typename F, typename... Args>
concept struct LvalueInvocable : Invocable<F&, Args...>
{ };

template <typename T, LvalueInvocable<T> F,
    typename U = LvalueInvocable<F, T const&>::result_type> // (*)
vector<U> fmap(F f, vector<T> const& ts)
{
    vector<U> us;
    us.reserve(ts.size());
    for (auto&& t : ts) {
        us.push_back(invoke(f, t)); // (*)
    }
    return us;
}
```

This is still wrong because the invocation doesn't necessarily match the constraint. Hopefully nobody actually uses `vector<bool>`{:.language-cpp} and we never have to find out, but in other algorithms these kinds of subtle errors will come up and it would be nice to get more help from the language in this endeavor. Maybe we get lucky and it happens to work. Maybe we passed in a function that was only invocable with _exactly_ `bool`{:.language-cpp} and this suddenly fails to compile. Maybe it returns a different type by accident. Anything could happen.

One way we could ensure we do the right thing is by using the fully qualified concept signature I demonstrated earlier. That is, instead of:

```cpp
invoke(f, t)
```

we use

```cpp
LvalueInvocable<F, T const&>::operator()(f, t)
```

This will definitely do the right thing. This is the constraint we laid out. It's also 47 characters instead of 13 and nobody outside of war-torn and battle-weary librarians will ever write it, and even they don't want to. 

But within this context, we know we're dealing with `LvalueInvocable<F, T const&>`{:.language-cpp}. That's in our declaration, it's one of the first things we write. Why do we have to keep repeating it? C++0x would implicitly let you access the associated aspects of that concept through the type directly - by way of transforming it. I'm instead proposing to let you _explicitly_ access those things, with a new access operator which I will spell `..`:

```cpp
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

This is a perfectly correct implementation (modulo dealing with those cases where `U` is a const or reference type). Access using `..` will look through _associated concepts_ of its left-hand operand for the names on the right-hand side, with operators implicitly abbreviated. In a dependent context, an associated concept is any declared constraint for a type - whether through a normal concept declaration or other first-class ways of declaring conformance (e.g. `static_assert`{:.language-cpp}, `if constexpr`{:.language-cpp}). In a non-dependent context, an associated concept is any concept visible in scope that happens to be satisfied by the left-hand operand (more examples of this later).

In the above example, `F`{:.language-cpp} has as an associated concept `LvalueInvocable<T const&>`{:.language-cpp}. As a result, `F..result_type`{:.language-cpp} is valid and is just syntax sugar for `LvalueInvocable<F, T const&>::result_type`{:.language-cpp}. Likewise, `f`, which is an `F`, can find `LvalueInvocable<F, T const&>::operator()`{:.language-cpp}. Remember that this particular call operator is _not a template_. It is effectively invoking an object with the signature `U operator()(F&, T const&)`{:.language-cpp}. This is what helps us _ensure_ that we do the right thing.

In the same way that unqualified lookup can find names in associated namespaces, and qualified lookup can find names where you tell it to... you can also use qualified concept lookup with this syntax. Which, in this case, would be `F..Invocable<T const&>::result_type`{:.language-cpp} and `f..Invocable<T const&>::operator()(t)`{:.language-cpp}. It's not shorter, but at least it reads left-to-right instead of inside-to-outside.

Now that we have a nice way of both declaring and implementing `fmap()`{:.language-cpp}, I think we can still do even better on the declaration side by putting the `result_type` even closer to `U`. What I mean by that is:

```cpp
template <typename T, typename U,
    LvalueInvocable<T const&, ..result_type=U> F>
vector<U> fmap(F, vector<T>);
```

This to me reads far more directly as "an lvalue invocable whose `result_type` is `U` for some `U`". This seems like a completely pointless distinction until we try to implement monadic bind. That is an algorithm which takes "an lvalue invocable whose `result_type` is `vector<U>`{:.language-cpp}":

```cpp
template <typename T, typename U,
    LvalueInvocable<T const&, ..result_type=vector<U>> F>
vector<U> bind(F, vector<T>);
```

Or the final boss of that blog post - implementing `sequence()`{:.language-cpp} over a `Range` whose `value_type` is some `expected<T, E>`{:.language-cpp}.

```cpp
template <typename T, typename E,
    Range<..value_type = expected<T, E>> R>
expected<vector<T>, E> sequence(R&&);
```

Wow is that pleasant to read! 

With a footnote that... of course, we have to go back and account for the fact that if a function returns a const or reference type before sticking it in a vector. That's going to be such a common thing to happen that I figure it's worth either coming up with a syntax for it either on the left hand side like `..result_type ~= U`{:.language-cpp} (meaning a `result_type` that decays to `U`) or the right hand side like `..result_type ~= U auto&&`{:.language-cpp} (which would be based on a separate language feature Michael Park and I are thinking about).

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

Two new things here. The syntax `typename Iterator iterator`{:.language-cpp} not only introduces an associated type but requires that it satisfy the concept `Iterator`{:.language-cpp}. And the concept `View`{:.language-cpp} is declared `explicit`{:.language-cpp}  meaning that it can only be satisfied explicitly, never implicitly. In this definition, `vector<int>`{:.language-cpp} implicitly models `Range` by the rules I've laid out above, but it doesn't model `View` because it doesn't explicitly do so. The above doesn't quite perfectly fit into C++20 Ranges because there's a special case of what it means to call `begin` on an rvalue, but this is still in early exploration stages.

The added associated types here mean that I can write something like:

```cpp
template <std::ranges::Range R>
void foo(R&& rng) {
    // std::ranges::Range is an associated concept of R, hence
    // I can access its associated types and functions
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
    // this concept (which must be done explicitly)
    virtual view_type view(T&&);
    
    // these are NOT virtual - they are neither checked to ensure
    // that a type satisfies ViewableRange, nor can they be
    // overriden. They are provided as associated functions so
    // they can be used with convenient syntax
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

All these adapters don't _have_ to live inside of `ViewableRange`. Users can extend this to write their own. The culmination of all this effort is that we can write:

```cpp
// explicitly bring in ViewableRange for all the adapter goodies
using concept std::Ranges::ViewableRange;

// write our own accumulate() algorithm too, as a concept
template <typename VR>
concept struct Accumulate : ViewableRange<VR>
{
    template <typename U,
        LvalueInvocable<U&&, VR..reference> F = std::plus>
            requires ConvertibleTo<F..result_type, U>
    U accumulate(VR&& rng, U init, F op = {})
    {
        // most people (including me) would probably write
        // auto&& here but I'm just writing the convenient type
        // name because it's there
        // also, rng..all() would be ill-formed (at the point
        // of definition) because ViewableRange is not an
        // associated type of VR&!
        for (VR..reference elem : FWD(rng)..all())
        {
            init = op..(std::move(init), elem);
        }
        return init;
    }
};

// and use all the things
bool is_even(int i) { return i % 2 == 0; }
std::vector<int> ints = {1, 2, 3, 4, 5, 6};

auto sum = ints..filter(is_even)
               ..transform([](int x){ return x * x; })
               ..accumulate(0);
assert(sum == 56);
```

Let's go through what all is going on here.

`ints..filter`{:.language-cpp} will look up all the associated concepts of `ints`{:.language-cpp} and find `ViewableRange` (explicitly brought in) and `Accumulate` (in scope). `std::vector<int>&`{:.language-cpp} implicitly models `Range`, lvalue `Range`s explicitly model `ViewableRange`, and `ViewableRange`s implicitly model `Accumulate`. So both concepts are viable.

We find the `filter` associated function in `ViewableRange` and invoke it (as `ViewableRange<std::vector<int>&>::filter(ints, is_even)`{:.language-cpp}). That returns some `View` (specifically `filter_view` but that's not really material). Any `View` models `ViewableRange`, so again we go through the process to find the `transform` associated function and invoke that. And lastly. And lastly we find `accumulate` by way of the implicitly satisfied concept `Accumulate`.

I, for one, think this is a really cool place to end up.

### Tuple-like and Variant-like

One of the places where we don't have concepts today that would be interesting to try to apply them would be the tuple-like concept (used by structured bindings) and the variant-like concept (eventually used by pattern matching). These are actually difficult to describe, but a rough sketch might be as follows.

```cpp
template <typename T>
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

### Type erasure

Yet another advantage of the pseudo-signature approach is how well it can interract with reflection. It should be quite possible to take our first concept:

```cpp
template <typename T>
concept struct Drawable {
    virtual void draw(T const&, std::ostream&);
};
```

... and turn that into a struct of function pointers using a fairly simple transformation:

```cpp
struct Drawable_erased {
    void (*draw)(void const*, std::ostream&);
};
```

... andd that struct can be constructed from anything that matches the concept:

```cpp
template <Drawable T>
Drawable_erased make_Drawable_erased() {
    return {
        .draw = +[](void const* ptr, std::ostream& os){
                return Drawable::draw(
                    *static_cast<T const*>(ptr), os);
            }
    };
};
```

And that's half way to being able to a standard type erasure library built on concepts. The other half is being able to declare a function named `draw` that invokes this pointer. All of this seems well in the purview of reflection and is something we're already working towards. Would be great if concepts played nicely too.

### Summary

In short, this design gives us a full customization system, with named conformance instead of structural conformance. It allows us to directly and easily opt-in to interfaces implicitly or explicitly, and use first class syntax in generic algorithms regardless of how the user chooses to opt-in (the "CS1" part of UFCS).

It gives us a new access syntax (`..`) that both provides syntax sugar to ensure that generic algorithms are using the constraints they say they want so that they're doing what they think they're doing, and gives us nice syntax for extension methods (the "CS2" part of UFCS). 

It also gives us CPOs for free and obviates the need for arbitrary type traits, and provides a path forward towards very complex customization and type erasure. 