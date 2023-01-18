---
layout: post
title: "Getting in trouble with mixed construction"
category: c++
tags:
 - c++
 - c++20
 - c++23
 - optional
---

Several years ago, I wrote a post about the complexities of implementing comparison operators for `optional<T>`: [Getting in trouble with mixed comparisons]({% post_url 2018-12-09-mixed-comparisons %}). That post was all about how, even just for `==`, making a few seemingly straightforward decisions leads to an ambiguity that different libraries handle differently.

Now is a good time to circle back to that same idea, except this time instead of talking about equality comparison, we're just going to talk about construction. This post is going to work through a bunch of cases of trying to construct an object of type `X` from an object of type `Y`.

## `Optional<T>` from `T`

Should `Optional<T>` be constructible from `T`? We need _some_ way of engaging the optional, and this seems like a pretty straightforward, reasonable, and expected way to do so.

I should also note that `Optional<T>`'s default constructor should also exist and construct the optional in a disengaged state, but I don't have much else to add on that particular topic.

Also for simplicitly, I"m just going to deal with copying today - so all the constructors are going to take `const&` parameters and check for copying.

```cpp
template <typename T>
class Optional {
public:
    Optional();

    Optional(T const& value)
        requires std::copy_constructible<T>;
};
```

## `Optional<T>` from `U`

Should `Optional<T>` be constructible from `U`, if `T` is constructible from `U`? This would be allowing `Optional<int>` to be constructed from a `long` or `Optional<string>` to be constructed from a `char const*`.

Similar converting constructors exist for other tuples (e.g. `tuple<int>` is constructible from `long`), so it seems reasonable to allow this one as well.

That gets us to this state:

```cpp
template <typename T>
class Optional {
public:
    Optional();

    template <typename U = T>
        requires std::constructible_from<T, U const&>
    Optional(U const& value);
};
```

Defaulting the template parameter to `T` is one of those things that seems pointless, but is actually useful to support brace initialization. That syntax allows the following to work:

```cpp
struct Point { int x; int y; };

Optional<Point> o({.x=1, .y=2});
```

## `Optional<T>` from `Optional<T>`

Surely an `Optional<int>` should be copy constructible.

## `Optional<T>` from `Optional<U>`

Should `Optional<int>` be constructible from `Optional<long>`? Should `Optional<string>` be constructible from `Optional<char const*>`?

For `std::tuple`, these conversions are all valid. And these conversions are all fairly straightforward to define - if the right-hand side is disengaged, we are constructed disengaged. Otherwise, we are constructed engaged from the right-hand side's value. There's no other possible meaning to this, so we might as well support it.

That gets us to:

```cpp
template <typename T>
class Optional {
public:
    Optional();

    // post: *this is engaged, with value v
    template <typename U = T>
        requires std::constructible_from<T, U const&>
    Optional(U const& v);

    // post: *this is engaged iff opt is engaged
    // if *this is engaged, then this->value() == opt.value()
    template <typename U>
        requires std::constructible_from<T, U const&>
    Optional(Optional<U> const& opt);
};
```

So far, so good. We're adding some nice conversions to our `Optional` and making it usable. None of these decisions seems particularly controversial either.

## `Optional<Optional<T>>` from `Optional<T>`

Given that `Optional<T>` should be constructible from `T`, that should still hold true when `T` happens to be some `Optional<U>`.

That is, this test should hold for all copy constructible types:

```cpp
template <typename T>
void test(T const& x) {
    Optional<T> opt(x);
    REQUIRE(opt);
    REQUIRE(*opt == x);
}
```

But... that's not what would actually happen in our implementation so far.

Given

```cpp
Optional<int> disengaged;
Optional<int> engaged(1);
```

Consider these constructions:

```
Optional<Optional<int>> from_disengaged(disengaged);
Optional<Optional<int>> from_engaged(engaged);
```

We have `T=Optional<int>`, and our two constructor options are:

1. `Optional(U const&)` with `U=Optional<int>`. This is viable because `T` is constructible from `U` (that's just copy construction).
2. `Optional(Optional<U> const&)` with `U=int`. This is viable because `T` is constructible from `U` (that's asking if `Optional<int>` is constructible from `int`).

Of these `(2)` is _more specialized_ (`Optional<U>` vs `U`) so it's the better match, and is what is preferred. As a result, what ends up happening is:

* `from_disengaged` is a disengaged optional (because `disengaged` is, as the name suggests, disengaged).
* `from_engaged` is an engaged optional containing the value `Optional<int>(1)`.

That first result violates our test case - we expect that constructing an `Optional<T>` from a `T` always gives us an engaged optional, whose value is `T` -- but here we got a disengaged optional instead.

This might seem like a fairly contrived situation, but we did run into this problem with my original implementation of `Optional`. Consider:

```cpp
template <typename T>
struct Vector {
    auto size() const -> size_t;
    auto operator[](size_t) const -> T const&;

    auto try_at(int idx) const -> Optional<T const&> {
        if (idx >= size()) {
            return {};
        }
        return (*this)[idx];
    }
};
```

Pretty straightforward looking code. `try_at` either gives you a reference to the element at index `idx` or returns a disengaged optional if that index is out of bounds.

Except if we had `Vector<Optional<V>>`:

* if the storage was disengaged, we'd get back a disengaged optional (instead of an engaged optional referring to _that_ disengaged optional)
* if the storage was engaged, we'd get back an engaged optional with a dangling reference

> It's worth explaining why a dangling reference. Here, we are trying to construct an `Optional<Optional<V> const&>` from an `Optional<V> const&`. In this case, we do **not** use the value constructor - recall that we're using the optional converting constructor: constructing an `Optional<T>` (with `T=Optional<V> const&`) from `Optional<U>` (with `U=V`). That works, because `Optional<V>` is constructible from `V`.
>
> But we're specifically constructing an `Optional<V> const&`.  That only works by first constructing a temporary `Optional<V>` and binding a reference to that. But then once we do so, that temporary is destroyed, and we're left with a dangling reference.
>
> This is why in our real implementation, we detected and rejected this conversion. So the whole thing didn't compile (which is still worse than working, but at least it's better than guaranteed undefined behavior). Thanks to Tim Song pursuing [P2255](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p2255r2.html) for C++23, the standard library has a type trait to reliably detect this case for any such future code.
{:.prompt-info}

It's hard to say that this `Vector::try_at` implementation is wrong, so it's important it work here too.

## `Optional<Optional<T>>` from `Optional<T>`, take 2

So one of these two constructors is wrong. Which one?

The approach the standard library takes, which you can see in [\[optional.ctor\]](https://eel.is/c++draft/optional.ctor) is this:

```cpp
template <typename T, typename W>
constexpr bool converts_from_any_cvref =
  disjunction_v<is_constructible<T, W&>, is_convertible<W&, T>,
                is_constructible<T, W>, is_convertible<W, T>,
                is_constructible<T, const W&>, is_convertible<const W&, T>,
                is_constructible<T, const W>, is_convertible<const W, T>>;

template <typename T>
class Optional {
public:
    Optional();

    // post: *this is engaged, with value value
    template <typename U = T>
        requires std::constructible_from<T, U const&>
    Optional(U const& value);

    // post: *this is engaged iff opt is engaged
    // if *this is engaged, then this->value() == *opt
    template <typename U>
        requires std::constructible_from<T, U const&>
             and (not converts_from_any_cvref<T, Optional<U>>)
    Optional(Optional<U> const& opt);
};
```

In short, the `Optional<T>` from `Optional<U>` constructor is only considered if `T` is not constructible from any kind of `Optional<U>` (the constraint checks for all of `W`, `W&`, `W const`, and `W const&`).

If we re-consider this example:

```cpp
Optional<int> disengaged;
Optional<int> engaged(1);
Optional<Optional<int>> from_disengaged(disengaged);
Optional<Optional<int>> from_engaged(engaged);
```

Now, neither the `from_disengaged` nor `from_engaged` constructors consider the `Optional<U>` construction - because there `T` (which is `Optional<int>`) is constructible from `Optional<U>` (which is also `Optional<int>`), so the value constructor is preferred to the converting optional constructor. And our test case passes.

The `Vector<T>::try_at` example also now works correctly, even when `T=Optional<U>`.

So we're all good right? Ship it.

## `Optional<bool>` from `Optional<int>`

Now consider this example:

```cpp
auto src = Optional<int>(0);
auto dst = Optional<bool>(src);
```

What is `dst`? You might expect this to be an example of constructing an `Optional<T>` from an `Optional<U>`, with `T=bool` and `U=int` -- and thus that `dst` is engaged (because `src` is engaged) with value `false` (which is `0` converted to `bool`).

But that's not what happens. Instead, `dst` is engaged with value `true`:, as you can see [here](https://godbolt.org/z/ePdW9bWKT).

Why?

Let's go through our constructors again:

* `Optional(U const&)` with `U=Optional<int>`. This is _viable_ because `bool` is, in fact, constructible from `Optional<int>` (because `Optional<T>` has an `explicit operator bool() const` for use in checking)
* `Optional(Optional<U> const&)` with `U=int`. This is initially viable because `bool` is constructible from `int`, but then we discard it because of the previous fix giving preference to the first constructor.

Pretty surprising outcome to most people, I would expect.

More generally, constructing an `Optional<bool>`, `o`, from an `Optional<T>`, `s` behaves as follows:

* if `T` is `bool`, this does copy construction. If `s` is disengaged, then `o` is also.
* Otherwise, if `s` is engaged (regardless of its value), then `o` is `Optional<bool>(true)`.
* Otherwise, `o` is `Optional<bool>(false)`.

That is, constructing an `Optional<bool>` from an `Optional<T>` for non-`bool` `T` _always_ gives you an engaged optional.

## `expected<bool, E1>` from `expected<bool, E2>`

C++23 is shipping with `std::expected<T, E>`, a useful error handling type. The construction rules for `std::expected<T, E>` are basically the same as those from `std::optional<T>` (except adjusted where appropriate since now we have two types).

And so there, we have the exact same problem, which is now [LWG 3836](https://cplusplus.github.io/LWG/issue3836):

```cpp
struct BaseError{};
struct DerivedError : BaseError{};

// e1 is a value equal to 5
auto e1 = std::expected<int, DerivedError>(5);

// e2 is a value equal to 5
auto e2 = std::expected<int, BaseError>(e1);

// e3 is a value equal to false
auto e3 = std::expected<bool, DerivedError>(false);

// e4 is a value equal to true???
auto e4 = std::expected<bool, BaseError>(e3);
```

This is the same problem: we can construct from a `U` (value constructor) or an `expected<U, F>` (converting constructor), but we only consider the converting constructor if the value constructor isn't viable - and here it is, because `std::expected<T, E>` (like `std::optional<T>`) is convertible to `bool`.

## The Boost approach

In my previous post on comparisons, I'd noted that `boost::optional` and `std::optional` have different behavior for the comparisons. Likewise, they also have different behavior for construction.

`boost::optional<T>`'s constructors look [like this](https://www.boost.org/doc/libs/1_81_0/libs/optional/doc/html/boost_optional/reference/header__boost_optional_optional_hpp_/header_optional_optional_values.html#reference_operator_template):

```cpp
namespace boost {

template <typename T>
class optional {
public:
    optional(T const&) requires std::copy_constructible<T>;

    template <typename U>
        requires std::constructible_from<T, U const&>
    explicit optional(optional<U> const&);
};

}
```

Note that the value constructor is just from `T`, not `U`.

The consequence of this design is that:

* constructing an `optional<optional<int>>` from an `optional<int>` prefers the first constructor. Originally, the logic I showed preferred the second because it was a more specialized function template than the first. But now, the first isn't a template, so it's preferred over the template in this case. Thus, we do the right thing (without having to add the extra constraint).
* constructing an `optional<bool>` from an `optional<int>` now prefers the second constructor - this is because the first isn't even viable. `optional`'s conversion to bool is `explicit`, so it wouldn't be considered in this context. Thus, we do the right thing here too: we use the optional converting constructor, rather than the value constructor.

But also:

* `char const*` isn't convertible to `optional<string>` since there aren't any valid constructors.

You can explore the differences [here](https://godbolt.org/z/59Yaxe89f).

## The Ambiguity

The fundamental issue here is that there's an ambiguity in constructing an `Optional<T>` from an `Optional<U>`, since there's two ways to interpret this construction:

* it's the value constructor: trying to construct an engaged optional, and the value we're constructing from simply happens to itself be an `Optional`
* it's the optional converting constructor: constructing a disengaged optional if the right-hand side is disengaged, otherwise constructing a value from the right-hand side's value.

But the syntax here is the same either way - `Optional<T>(src)` - so the library has to do its best to try to do The Right Thing with no help. The standard library does this one way (which gets it right most of the time, except for `bool`) and Boost does it another way (which seems to get it right all the time, but has less functionality).

Is there another way to do it?

### The bool exception

We could treat `bool` as special - on the basis that `std::optional<T>` and `std::expected<T, E>` are always (explicitly) convertible to `bool`, regardless of `T` and `E`.

That is, something like this:

```cpp
template <typename T>
struct Optional {
    template <typename U>
        requires std::constructible_from<T, U const&>
    Optional(U const&);

    template <typename U>
        requires std::constructible_from<T, U const&>
             and (not std::constructible_from<T, Optional<U> const&>
                  or std::same_as<T, bool>)
    Optional(Optional<U> const&);
};
```

Now, constructing `Optional<bool>` from `Optional<int>` would consider the second constructor, which now becomes the better match on the basis of being more specialized.

This would solve the problem for `bool`, but while `bool` is special (in that `Optional` is specifically convertible to it), there are other types that would continue to behave weirdly.

Like `Optional<std::any>`.

### The explicit approach

Here's a different approach. `Optional` has continuation (aka monadic) functions now, so it's straightforward to convert an `Optional<T>` to an `Optional<U>` if so desired:

```cpp
auto src = Optional<T>(/* ... */);

// with converting constructor
auto dst1 = Optional<U>(src);

// with map
auto dst2 = src.map(static_cast_<U>);
```

Now, with `std::optional<T>` this is actually spelled `transform` and there's no function object in the standard library that does `static_cast<T>` (which is both unfortunate as it's a useful object to have lying around, and also because it'd be especially nice if it could just be spelled `static_cast<T>` rather than `std::static_cast_<T>` or something to that effect).

We could then use this design for constructors:

```cpp
template <typename T>
struct Optional {
    Optional(T const&) requires std::copy_constructible<T>;

    template <typename U>
        requires std::constructible_from<T, U const&>
    Optional(U const&);

    Optional(Optional const&) = default;
};
```

This handles the `Optional<Optional<T>>` from `Optional<T>` problem by there simply only being one candidate: the value constructor, which is the desired constructor to use.

But... this still has the `Optional<bool>` from `Optional<int>` problem because we deduce `U=Optional<int>` and `bool` is constructible from that, so `Optional<bool>(Optional<int>(0))` would give us `Optional<bool>(true)`.

### The explicit approach, take 2

Since providing any kind of converting constructor is out, so let's provide none of them:

```cpp
template <typename T>
struct Optional {
    Optional(T const&) requires std::copy_constructible<T>;

    Optional(Optional const&) = default;
};
```

Here we don't have any of the wrong behavior (since `Optional<bool>` isn't even constructible from `Optional<int>`, and constructing an `Optional<Optional<int>>` from `Optional<int>` only has one way of getting there).

But we're also missing some of the good behavior. You can still convert one `Optional` to another via `map`, but converting via value has to be explicit (or `explicit`):

```cpp
Optional<std::string> a = "hello";              // error
Optional<std::string> b("hello");               // ok
Optional<std::string> c = std::string("hello"); // ok
```

Another approach here would be to make the value construction _even more explicit_ while also allowing implicit conversions. We can do that using this pattern:

```cpp
template <typename T>
struct Some {
    T value;
};

template <typename T>
struct Optional {
    template <typename U>
        requires std::constructible_from<T, U const&>
    Optional(Some<U> const&);

    Optional(Optional const&) = default;
};
```

Here, we simply require the user to be quite clear in what they're doing:

```cpp
Optional<int> a = 42;                     // error
Optional<int> b{42};                      // still error
Optional<int> c = Some(42);               // ok
Optional<std::string>> d = Some("hello"); // ok
```

That is, we avoid the ambiguity by having the two syntaxes simply be different. If I want to construct an engaged `Optional<T>` from a `T` or a `U`, that looks like this:

```cpp
Optional<T> from_value = Some(value);
```

And if I want to convert an `Optional<U>` to an `Optional<T>`, that looks like this:

```cpp
Optional<T> convert_opt = opt.map(static_cast_<T>);
```

Although, as the section heading suggests, this is more explicit - which means it requires more syntax. Today, both of those constructs are simply:

```cpp
auto from_value = Optional<T>(value);
auto convert_opt = Optional<T>(opt);
```

## Conclusion

Implementing the constructors for `Optional<T>` seems like a fairly simple problem, but once you make a few seemingly straightforward choices to improve ergonomics (allowing construction from `T`, `U`, and `Optional<U>`), you run into ambiguity issues that could lead to surprising and unexpected behavior.

The only real way to reduce the surprise is to prune back the ergonomics and require the user to be more explicit in expressing their intent. Then again, was it really ergonomic if it gave you the wrong answer?

Currently the `bool` construction issue exists in both `std::optional` and `std::expected`. There's an open library issue  ([LWG 3836](https://cplusplus.github.io/LWG/issue3836)) for the `std::expected` one specifically, but given that it has the same behavior as `std::optional`, it would be hard to change. Any change to `std::optional` at this point would certainly break code, and having `std::expected` behave consistently with `std::optional` seems like the right place to be.

At Jump, when I first implemented `Optional`, I had originally (for reasons I do not recall) attempted a different ruleset  to attempt to distinguish which way we were constructing our `Optional<T>` from an `Optional<U>`:

* `Optional<T>` is constructible from `U` when `U` is not some `Optional` and `T` is constructible from `U`
* `Optional<T>` is constructible from `Optional<U>` when `T` is constructible from `U`

That is, constructing from `Optional<U>` _always_ was treated as a converting optional construction and never a value construction. This is one way of avoiding the `Optional<bool>` constructin problem, but it also [violated](#optionaloptionalt-from-optionalt) the principle that constructing an `Optional<T>` from a `T` always gives you an engaged `Optional` whose value is `T`.

As with all generic choices like this - it worked fine until it suddenly didn't, and we ran into problems with something like the `Vector` example earlier. So now Jump's `Optional` does the same thing that the standard library's does (at least in this particular instance). Which means that while constructing an `Optional<Optional<T>>` from an `Optional<T>` always works and does the right thing, we have the `Optional<bool>` from `Optional<T>` problem.

`Optional<bool>` isn't a very common type, and it's an annoyingly inefficient one at that (at least until [P2641](https://wg21.link/p2641) gets adopted), so it seems like it's really not that big of a deal -- better to get the ergonomics for all the other situations (converting value and converting optional).

But when you have enough users, somebody will eventually run into it. And when they do run into it, it's not an easy bug to track down (although it is very easy to fix).

> Completely incidentally, somebody ran into that problem with our implementation recently.
{:.prompt-info}

In this case, it seems like there are four possible choices to make:

1. the standard implementation: gets `Optional<bool>` from `Optional<T>` wrong, but everything else right, and supports all the ergonomic conversions
2. the `bool` exception implementation: gets `Optional<bool>` from `Optional<T>` right, but still gets `Optional<any>` from `Optional<T>` wrong. Still supports all the ergonomic conversions.
3. the boost implementation: gets everything right, supports constructing `Optional<T>` from `Optional<U>` but not `Optional<T>` from `U`.
4. the explicit implementation: gets everything right, requires constructing from `Some`

(1) is unfortunately broken (albeit rarely), (2) feels like a hack, (3) will break some code, (4) will break a lot of code but is the most obviously correct by construction.

It's hard to know what the correct choice is. If existing code weren't a concern though, (4) does seem attractive. After all, if we had language variants, that's what we'd do.
