---
layout: post
title: "Why were abbrev. lambdas rejected?"
category: c++
tags:
  - c++
  - c++20
  - lambda
---

In November, 2017, I presented my proposal for abbreviated lambdas
([P0573R2](https://wg21.link/p0573r2)) to Evolution in Albuquerque. It
was rejected (6-17), though the group was willing to consider future proposals
for shorter lambdas which present new technical information (18-2).

Since then, there's been a lot of confusion about what actually happened and why
it was rejected, and part of this was my fault for not doing a good job
communicating this to interested parties. Actually, that's generous - I didn't
really communicate anything. So here is my making up for lost time by actually
conveying this information.

To summarize, the core of the abbreviated lambda paper was that the syntax:

```cpp
[](auto&& a, auto&& b) => a.id() < b.id();
```

mean _precisely_:

```cpp
[](auto&& a, auto&& b)
    -> decltype((a.id() < b.id()))
    noexcept(noexcept(a.id() < b.id()))
{
    return a.id() < b.id();
}
```

Because [you must type it three times](https://www.youtube.com/watch?v=I3T4lePH-yA).

The paper also had two extensions. The same syntax for functions:

```cpp
template <typename C> auto begin(C& c) => c.begin();
```

And going one step further and allowing omitting type names:

```cpp
[](a, b) => a.id() < b.id()
```

Where the last lambda would mean precisely the same as the first example, just
saving us having to type the two `auto&&`{:.language-cpp}s.

This proposal was rejected for several reasons. Let's go through them.

### Differing semantics with regular lambdas

Consider the two lambdas which just dereference a pointer:

```cpp
auto f = [](int const* p) { return *p; }
auto g = [](int const* p) => *p;
```

`f` returns an `int`{:.language-cpp}. `g` returns an `int const&`{:.language-cpp}. C++ is a value semantic
language, that is copy by default [^1], here would be a place where suddenly
we're implicitly providing references. Moreover, some lambdas have `auto`{:.language-cpp}
semantics implicitly while abbreviated lambdas have `decltype(auto)`{:.language-cpp} semantics
implicitly.

Two different semantic models for basically the same feature.

### Arbitrary lookahead parsing

With trying to omit type names, consider the beginning of the expression
`[](a, b)`{:.language-cpp}. This looks like a lambda that takes two (unnamed) parameters of
types `a` and `b`. But with the paper, it _could_ be the beginning of an abbreviated
_generic_ lambda takes two parameters of types `auto&&`{:.language-cpp} and `auto&&`{:.language-cpp}. We don't
know how to interpret the parameter list until we eventually see a `=>`{:.language-cpp} (or not).

There was very strong opposition on this point.

### Mismatch between the _trailing-return-type_ and the body

**Update** My paper addressing this issue, [P2036](https://wg21.link/p2036), was
adopted in October 2021 as a defect report that fully addresses the issue
described in the following section. Progress!

One of the subtleties with lambdas today is that name lookup in the
_trailing-return-type_ and the body of a lambda actually behave differently.
Sometimes. Or rather, they always behave differently, but quite frequently
the result is the same so you may not have noticed.

Consider a simple function that composes two functions, implemented with a
lambda:

```cpp
template <typename F, typename G>
auto compose(F f, G g) {
    return [=](auto... args) -> decltype(f(g(args...))) {
        return f(g(args...));
    };
}
```

This implementation seems perfectly reasonable: we're trying to write a SFINAE-
friendly composition, and we want to preserve references. But it's very
subtly wrong.

Here's one example:

```cpp
auto counter = [i=0]() mutable { return i++; };
auto square = [](int i) { return i*i;};

auto squares = compose(square, counter);

// this passes: squares is invocable with no arguments.
static_assert(std::is_invocable_v<decltype(squares)>);

// this is a compile error
auto next = squares();
```

We verified that our function is invocable, and yet we cannot invoke it. Why
not? Because in the _trailing-return-type_, `f` and `g` have types `F` and `G`,
and so the expression `f(g())`{:.language-cpp} is a valid expression whose type is `int`{:.language-cpp}.
But in the body, `f` and `g` are "members" of a lambda whose call operator is
`const`{:.language-cpp} and hence they behave as `F const`{:.language-cpp} and `G const`{:.language-cpp}

### Where to go from here

As I said at the beginning, the room said they were amenable to seeing a new proposal
with new technical information. Unfortunately, the first issue I pointed out
here (having a differing semantic model) isn't really a technical problem - it's
not like there are implementation or specification or even comprehension
difficulties with this approach. So there would have to be a new design that
somehow makes it visible that we're (potentially) returning a reference.

This isn't easy because references decay - we could easily regain `auto`{:.language-cpp}
semantics by adopting Zhihao's [P0849](https://wg21.link/p0849) and having
an abbreviated lambda end with `=> auto(expr)`{:.language-cpp} instead of
`=> expr`{:.language-cpp}. But we have no way of going the other way, and the
most natural [^2] choice might be `=> decltype(auto)(expr)`{:.language-cpp} but
that would already have meaning. It'd need to be something novel like
`=> ref expr`{:.language-cpp} or come up with a different token than `=>`{:.language-cpp}
for when we want reference semantics.

Or, we could take a wildly different approach. Perhaps we pursue something like
an [expression lambda](https://vector-of-bool.github.io/2018/10/31/become-perl.html).
Maybe that falls into the same fundamental problem - maybe it's a sufficiently
different construct that's more tightly defined as being _that expression_ that
it works. Such an approach would be well shorter than what my paper proposed
as well. Here's a simple example for producing a comparator based on a member
function (a context where SFINAE and reference-preservation are unlikely to
be important):

```cpp
// C++14 (50 chars)
[](auto&& a, auto&& b) { return a.id() < b.id(); }

// P0573, without typename omission (41 chars)
[](auto&& a, auto&& b) => a.id() < b.id()

// Swift (17 chars)
$1.id() < $2.id()

// vector-of-bool's blog suggestion (21 chars)
[][&1.id() < &2.id()]
```

But the point of this blog isn't to suggest what the right direction is or isn't,
I just wanted to write a long overdue summary of at least what questions need
to be considered to even take another step - wherever that next step might lead.


[^1]: Except for when you write `f(value)`{:.language-cpp} and have no idea if `value` will be copied or not.
[^2]: Did I just call this natural? C++ is weird.
