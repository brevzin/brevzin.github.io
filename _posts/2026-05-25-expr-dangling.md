---
layout: post
title: "Trying to avoid dangling in new kinds of expressions"
category: c++
tags:
 - c++
 - c++29
pubdraft: yes
---

C++26 is all wrapped up, so time to start thinking about C++29. Of course there are many things I'd like to do in the reflection space (and I got to deliver a [keynote](https://youtu.be/DZTkT1Cq_aY?si=CSbPSx6T4JQSwW_N) at C++Now this year giving my thoughts on that problem), but this post isn't about reflection. Instead, it's about expressions.

I'm hoping C++29 will give us more expression tools, led by [pattern matching](https://wg21.link/p2688). But less significant than pattern matching are two other expression kinds that I'm working on:

* [`do` expressions](https://wg21.link/p2806) (with Bruno Cardoso Lopes, Zach Laine, and Michael Park) — adding block expressions to C++, as an enhancement/improvement to the gcc statement-expression extension
* [a control flow operator](https://wg21.link/p2561) — an ergonomic way to use `optional`/`expected` types, similar to Rust's `?` operator.

> In C++, the control flow operator syntax cannot be `expr?` due to ambiguity with the conditional (ternary) operator. But for the purposes of this post, I'll use that syntax anyway, since people will be familiar with it, and this post isn't about syntax anyway.
{:.prompt-info}

Now, the `?` operator can seemingly be defined simply in terms of a `do` expression. `expr?`, after all, is basically:

```cpp
do -> ReturnType {
    auto&& __r = expr;
    if (not __r) {
        // It turns out that in C++, figuring out the best
        // way to spell this return expression is its own
        // problem (see the paper), but this post isn't about
        // that problem either, so I'll mostly ignore it here.
        return /* ... */;
    }

    // This is std::forward<decltype(__r)>(__r). But I don't
    // like that both because it's very verbose and also because
    // it forces you to write a unary operation (forwarding)
    // as if it were a binary operation. So I use a macro.
    *FWD(__r)
}
```

The question is: what type should `ReturnType` be?

If `expr` is an lvalue of type `std::optional<T>` or `std::expected<T, E>`, then `ReturnType` should pretty straightforwardly be `T&`. It would be surprising (and unnecessary) to make a copy in this case.

But if `expr` is an rvalue, the question becomes more interesting: should this be `T` (incurring an extra move, which may or may not get optimized out) or `T&&` (which may be more efficient, but may dangle)?

## Status Quo

Today, we have neither `expr?` nor `do` expressions. We have the GCC statement-expression extension, but that one is actually always a prvalue — always `T`. So it doesn't do much in the way of informing us.

In our codebase, we have a macro to provide an ergonomic way of doing `expected`-based error handling. That macro is probably quite similar to what a lot of other people use. It is a statement macro, not an expression macro:

```cpp
TRY(target, expr);
```

Which expands to, roughly:

```cpp
auto&& __r = expr;
if (not __r) {
    // again, doesn't matter
    return /* ... */;
}
target = *FWD(__r);
```

Note here that `target` is just anything that can go on the left-hand-side of `=`, so it can both be a declaration (typically `auto var` or `auto&& var`) or an assignment. Both are useful.

Note also that if we write `TRY(auto&& var, expr);` that `var` will be some reference into `__r`, which is in the same scope as `var` and outlives it. No concerns with dangling here, no extra moves.

But it's a statement, not an expression, so of course it's not as nice to use as an expression would be — it would be nice if introducing a new expression kind could be strictly superior to the macro. Otherwise, why bother?

## Dangling Problem I

The first dangling problem arises by simply trying to define `expr?` as

```cpp
do -> decltype(auto) {
    auto&& __r = expr;
    if (not __r) { return /* ... */; }
    *FWD(__r)
}
```

Because if this:

```cpp
auto get() -> std::optional<int>;

auto f() -> std::optional<int> {
    auto&& var = get()?;
    // ...
}
```

Evaluates as this:


```cpp
auto f() -> std::optional<int> {
    auto&& var = do -> decltype(auto) {
        auto&& __r = get();  // <--------------+
        if (not __r) { return std::nullopt; }  |
        *FWD(__r) // <-------------------------+
    };
    // ...
}
```

Then `__r` is going to be destroyed at the `}` following the usual C++ rules. `*FWD(__r)` returns a reference into `__r`, so `var` is going to be initialized with a reference to an already-destroyed object.

What can we do to resolve this?

It is tempting to say that we can solve this problem by just requiring/ensuring that `expr?` is just never an rvalue reference — forcing this case to return `int`. And indeed that would avoid dangling here. Moreover, it's probably more performant to return `int` instead of` int&&` here anyway (assuming it would even compile to different code to begin with).

But it turns out that you can run into dangling even without references...

## Dangling Problem II

Lauri Vasama showed me the following example. Let's imagine we have the following functions:

```cpp
auto get_data() -> std::vector<int>;

auto find_interesting(std::vector<int> const& data)
    -> std::expected<std::span<int const>, std::string>;

auto best_of(std::span<int const> data) -> int;
```

Here, `get_data()` gives me some data. `find_interesting()` might pull out an interesting section of that data, but it might fail. And then `best_of()` returns the best piece of data.

It would be reasonable to write something like this then:

```cpp
auto do_something() -> std::expected<int, std::string> {
    int value = best_of(find_interesting(get_data())?);
    // ... do something else with value ...
    return value;
}
```

It is one of the nice aspects of the `?` approach (regardless of what syntax we end up with) is that you really get the minimal amount of syntax addition to do explicit error handling.

> Of course with exceptions, there is zero additional syntax, which both why some people really like exceptions and why other people really dislike exceptions. I'm not trying to litigate exceptions here.
{:.prompt-info}

In that expression, `get_data()` is a temporary — and following the usual rules of temporaries, it lasts to the end of the full-expression. So the fact that `find_interesting` is taking a `span` into it is totally fine — nothing dangles here.

Now let's use our proposed `do` expression rewrite — which we'll even have the `do` expression explicitly return a value instead of a reference:


```cpp
auto do_something() -> std::expected<int, std::string> {
    int value = best_of(do -> std::span<int const> {
        auto&& __r = find_interesting(get_data());
        if (not __r) {
            return std::unexpected(FWD(__r).error());
        }
        *FWD(__r)
    });
    // ... do something else with value ...
    return value;
}
```

Does this work? Well, I probably wouldn't have asked if the answer was yes. So, indeed, the answer is no.

`get_data()` is still a temporary here, and it's destroyed at the `;` — but now it's destroyed at a different `;`. It's destroyed before the `do` expression finishes evaluating, so that simple rewrite ends up passing a dangling `std::span` into `best_of`.

That's... not good.

## The macro trap

One of the things I'm concerned about with these papers is the macro trap. Basically: what if we adopt `do` expressions but not the `?` operator? `do` expressions are more broadly useful, so if I could pick exactly one, that would certainly be the one I would pick.

But if we do that, then somebody (probably multiple somebodies) will attempt to implement an expression macro for control flow propagation as an improvement for the statement macro I showed earlier:

```cpp
#define TRY(expr)               \
    do {                        \
        auto&& __r = expr;      \
        if (not __r) {          \
            return something;   \
        }                       \
        *FWD(__r)               \
    }
```

That formulation gives you a dangling `span` for this example, even though the code _looks_ right:

```cpp
auto do_something() -> std::expected<int, std::string> {
    int value = best_of(TRY(find_interesting(get_data())));
    // ... do something else with value ...
    return value;
}
```

This _looks_ okay because it _looks_ like `get_data()` lasts to the `;` but that's not what happens with this rewrite. It dangles, even though our `do` expression rewrite doesn't even produce a reference.

I would like to avoid this trap.

> Note that this trap is pre-existing. In the statement macro formulation, had I written this, it would still dangle:
>
> ```cpp
> auto do_something() -> std::expected<int, std::string> {
>    TRY(auto interesting, find_interesting(get_data()));
>    int value = best_of(interesting);
>    // ...
> }
> ```
>
> I'd just like to aspire to do better.
{:.prompt-info}

## A reverse capture approach

The best way I can think of to avoid the macro trap is to come up with a way to ensure that an expression gets put in the _outer_ expression (i.e. the one that lexically in the source code the user wrote) rather than in the _inner_ expression (the `do` expression the macro expands to).

That is, conceptually, a lot like lambda _init-capture_ except that it's more like... an _init-hoist_? _outer-init_? _init-promote_?

> Naming is hard.
{:.prompt-info}

Anyway, however we name this thing, the macro could instead expand into something like this:

```cpp
auto do_something() -> std::expected<int, std::string> {
    int value = best_of(
        do [__r = find_interesting(get_data())]
        // ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        //            init-hoist?
            -> std::span<int const>
        {
            if (not __r) {
                return std::unexpected(FWD(__r).error());
            }
            *FWD(__r)
        }
    );
    // ... do something else with value ...
    return value;
}
```

Now, the temporary `get_data()` is in the outer expression, not the inner one, so would get destroyed at the right spot. Syntactically awkward I guess, but semantically it does avoid this problem — which I think is good.

That is, our expression-macro formulation of `TRY` could be defined as:

```cpp
#define TRY(expr)               \
    do [__r = expr] {           \
        if (not __r) {          \
            return something;   \
        }                       \
        *FWD(__r)               \
    }
```

No more macro trap. No more dangling.

Well, no more macro trap anyway.

> Interestingly enough, pattern matching offers a different way to solve this issue in a way that avoids the need for an init-hoist facility on `do` expressions. Rather than desugaring `expr?` into:
> ```cpp
> do [__r = expr] -> R {
>   if (not __r) { return something; }
>   *FWD(__r)
> }
> ```
> We could desugar it into:
> ```cpp
> expr match -> R {
>     let __r => do -> R {
>         if (not __r) { return something; }
>         *FWD(__r)
>     }
> }
> ```
> With the `match` expression, `expr` is (obviously) evaluated in the outer expression, and so any temporaries naturally last until the end of the (outer) full-expression as desired. The interesting question is: do we need to add an init-hoist feature for `do` expressions (a feature in no small part motivated by pattern matching) if pattern matching could solve it for us?
{:.prompt-info}

## Back to the first dangling problem

Let's get back to the first problem. What does this do:

```cpp
auto get() -> std::optional<int>;

auto f() -> std::optional<int> {
    // either this
    auto&& var1 = get()?;

    // or this
    auto&& var2 = TRY(get());

    // ...
}
```

Regardless of whether `?` is a language feature or a macro, we have to ask the question of what this actually does.

Firstly, we could say that `get()?` yields an `int&&` as expected and that this just dangles. Don't do that. That's a very C++ answer. And is a little unsatisfying to me because, as I showed earlier, `TRY(auto&& var, get());` does work and not dangle.

> However, given an `id()` function template that just forwards its argument, a different formulation like `TRY(auto&& var, id(get()));` would no matter what.
{:.prompt-info}

Secondly, we can just require/ensure that `expr?` is never an rvalue reference — and force this case to return `int`. That's totally fine for many cases, but it would be nice to not have to incur a move — it's completely unnecessary overhead in a lot of cases and really is only beneficial in this specific use (albeit likely a common one).

> In Rust, the `expr?` desugars into
> ```rust
> match Try::branch(expr) {
>     ControlFlow::Continue(v) => v,
>     ControlFlow::Break(r) => return FromResidual::from_residual(r),
> }
> ```
> which always moves from `expr` since `Try::branch` takes `self`{:.lang-rust}. But moves in Rust are always `memcpy`, so the calculus there is different.
{:.prompt-info}

Thirdly, we could recognize that when we see `get()?` that we can have the expectation (from a language perspective) that we're not `return`-ing, that we're going to get some part of `get()` back. So in the same way that we get lifetime-extension when we do this:

```cpp
// this looks like like T object is destroyed and we're
// left with a dangling reference, but actually the T
// is lifetime-extended
auto&& var = T().member;
```

We could just, by fiat, say that the same thing happens when we do this:

```cpp
auto&& var = get()?;
```

Which means that `expr?` doesn't exactly desugar into a `do` expression — in the same way that a range-based `for` loop doesn't actually desugar to a regular `for` loop due to the differing rules for treatment of temporaries. The consequence of that would be:

```cpp
auto&& a = get()?;     // the optional is lifetime-extended, doesn't dangle
auto   b = get()?;     // the optional is destroyed here, doesn't dangle
auto&& c = TRY(get()); // no special treatment, dangles
```

That's a little underwhelming from my perspective, but perhaps not the end of the world. Although note that this doesn't save us a lot either since, again given `id`:

```cpp
auto&& d = id(get())?;  // dangles
auto&& e = id(get()?);  // dangles
```

Fourthly, we could come up with... some mechanism to be able to annotate the variables declared in the `do`-expression's _init-hoist_ (I'm sticking with this) such that they would get lifetime-extended if the result of the expression is bound to a reference. Which is to say, some [attribute]({% post_url 2025-03-25-attributes %}):

```cpp
#define TRY(expr)                                  \
    do [ [[keep_me_around]] __r = expr] {          \
        if (not __r) {                             \
            return something;                      \
        }                                          \
        *FWD(__r)                                  \
    }
```

But this is now adding a lot of increasingly complicated extra stuff onto `do`-expressions. So much for just a block expression?

Fifthly, we could go one step further with the _init-hoist_ and actually throw those variables into the _outer_ scope. So that really

```cpp
{
    auto&& var = TRY(get());
}
```

evaluates more like this:

```cpp
{
    auto&& __r = get(); // <== out here, same as var
    auto&& var = do {
        if (not __r) return something;
        *FWD(__r)
    };
}
```

Which now obviously doesn't dangle because `__r` is in scope the whole time, but seems very leaky. This is exactly what we do with our `TRY` statement-macro, but would it be what we want from the expression-macro?

Is there a sixth option? I am not sure.

## So what do we do?

It's certainly a question.

If we ship `do`-expressions and a version of the `?` operator at the same time, then we don't need to worry about people implementing their own `TRY` macro, since `?` directly wouldn't have any surprises with temporary lifetimes. But that's probably far from the only situation in which the [macro trap](#the-macro-trap) would arise, just the easiest one to think of, so it's likely something we should try to preemptively solve.

Of the solutions I enumerated, the simplest by far (and probably the only viable options really) are the first two, which I might summarize as:

1. Yeah, it might dangle, so what?
2. You can't get a dangling rvalue reference if you can never get an rvalue reference.

In other words, the latter is desugaring `expr?` as:

```cpp
do [__r = expr] -> decltype(auto) {
    if (not __r) { return /* ... */; }
    DECAY_XVALUE(*FWD(__r))
}
```

where `DECAY_XVALUE` is defined as:

```cpp
#define DECAY_XVALUE(expr) \
    static_cast<[: remove_rvalue_reference(^^decltype((expr))) :]>(expr)
```

> This is simpler than it probably looks. For prvalues, this is `static_cast<T>(expr)`, which is a no-op. For lvalues, this is `static_cast<T&>(expr)`, which is a no-op. For xvalues, this is `static_cast<T>(expr)`, which is a forced move.
{:.prompt-info}

Now, the claimed benefit of "it might dangle, so what?" over "never give an rvalue reference" is efficiency — don't need to incur additional moves. But we only occur additional moves if they're not optimized out. After all, the Rust desugaring of `?` a move (two even, I think).

I thought it might be worth examining that claim. It turns out that I actually have an implementation of `do` expressions up on compiler explorer, so we can just compare the assembly. Except when doing this comparison, we will actually implement the `TRY` macro to do what I propose in the control operator paper, complete with `try_traits`. That full implementation is:

```cpp
#define TRY(e) do (auto&& __r = e;) -> decltype(auto) {             \
    using CT = try_traits<std::remove_cvref_t<decltype(__r)>>;      \
    using RT = try_traits<typename                                  \
        [: return_type_of(std::meta::current_function()) :]>;       \
    if (not CT::should_continue(__r)) {                             \
        return RT::from_break(CT::extract_break(FWD(__r)));         \
    }                                                               \
    DECAY_XVALUE(CT::extract_continue(FWD(__r)))                    \
}
```

And similar for my comparison `TRY_STMT` macro:

```cpp
#define TRY_STMT(tgt, e)                                          \
    auto&& __r = e;                                               \
    using CT = try_traits<std::remove_cvref_t<decltype(__r)>>;    \
    using RT = try_traits<typename                                \
        [: return_type_of(std::meta::current_function()) :]>;     \
    if (not CT::should_continue(__r)) {                           \
        return RT::from_break(CT::extract_break(FWD(__r)));       \
    }                                                             \
    tgt = CT::extract_continue(FWD(__r))
```

In both cases a production implementation would want to guard against name clashes, but this is good enough for now.

Let's start with the simplest comparison. We have some function that gives us data (or not):

```cpp
enum class E { };

template <class T>
auto get_data() -> std::expected<T, E>;
```

If we're getting _just_ getting an `int` and just returning it (via `TRY`), that leads to [identical code-gen](https://compiler-explorer.com/z/fjM6vxjMT):

```cpp
auto NAMED(consume_int)() -> std::expected<int, E> {
    #ifdef USE_STMT
    TRY_STMT(auto&& data, get_data<int>());
    #else
    auto&& data = TRY(get_data<int>());
    #endif
    return data;
}
```

> The `NAMED` macro here is just something I like to use for comparisons on compiler explorer to make sure that if I'm comparing code-gen from different configurations that I actually configured it correctly and I can clearly see in the result which one is which. In this case, I see a `consume_int_do_expr` function vs a `consume_int_stmt_macro` function.
{:.prompt-info}

Okay, that's maybe not surprising. What if we pick a type whose move construction actually _does something_? For instance: `std::unique_ptr<int>`. And let's now return `*data` instead. [That is](https://compiler-explorer.com/z/oW8xePPhK):

```cpp
auto NAMED(consume_uniq_ptr)() -> std::expected<int, E> {
    #ifdef USE_STMT
    TRY_STMT(auto&& data, get_data<std::unique_ptr<int>>());
    #else
    auto&& data = TRY(get_data<std::unique_ptr<int>>());
    #endif
    return *data;
}
```

This is interesting, because one of these approaches has an unnecessary store that wasn't optimized out — a `mov qword ptr [rsp], 0`{:.lang-nasm}. But it's actually the statement macro approach, not the do expression approach.