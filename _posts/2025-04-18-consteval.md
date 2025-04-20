---
layout: post
title: "Surprising consequences of <code class=\"language-cpp\">consteval</code> propagation"
category: c++
tags:
 - c++
 - c++23
 - constexpr
pubdraft: yes
permalink: consteval-propagation
---

One of the nice things about the `{fmt}` library (now also `std::format`) is that we get compile-time type checking of formatting arguments. Consider this example:

```cpp
#include <fmt/format.h>

int main() {
    []{
        fmt::print("x={}");
    }();
}
```

The immediately-invoked lambda admittedly looks a bit silly, but indulge me for a moment. That's not a valid formatting call — we have one replacement field (that's `{}`) but no argument for it. And, as desired, the program doesn't compile:

```
In file included from /opt/compiler-explorer/libs/fmt/trunk/include/fmt/format.h:41,
                 from <source>:1:
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h: In lambda function:
<source>:5:19:   in 'constexpr' expansion of 'fmt::v11::fstring<>("x={}")'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:2733:53:   in 'constexpr' expansion of 'fmt::v11::detail::parse_format_string<char, format_string_checker<char, 0, 0, false> >(fmt::v11::basic_string_view<char>(((const char*)s)), fmt::v11::detail::format_string_checker<char, 0, 0, false>(fmt::v11::basic_string_view<char>(((const char*)s)), (fmt::v11::fstring<>::arg_pack(), fmt::v11::fstring<>::arg_pack())))'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:1635:42:   in 'constexpr' expansion of 'fmt::v11::detail::parse_replacement_field<char, format_string_checker<char, 0, 0, false>&>((p + -1), end, (* & handler))'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:1592:51:   in 'constexpr' expansion of '(& handler)->fmt::v11::detail::format_string_checker<char, 0, 0, false>::on_arg_id()'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:1702:70:   in 'constexpr' expansion of '((fmt::v11::detail::format_string_checker<char, 0, 0, false>*)this)->fmt::v11::detail::format_string_checker<char, 0, 0, false>::context_.fmt::v11::detail::compile_parse_context<char>::next_arg_id()'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:1241:31:   in 'constexpr' expansion of '((fmt::v11::detail::compile_parse_context<char>*)this)->fmt::v11::detail::compile_parse_context<char>::<anonymous>.fmt::v11::parse_context<char>::next_arg_id()'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:906:20:   in 'constexpr' expansion of '((fmt::v11::parse_context<char>*)this)->fmt::v11::parse_context<char>::do_check_arg_id(id)'
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:2438:48: error: call to non-'constexpr' function 'void fmt::v11::report_error(const char*)'
 2438 |     if (arg_id >= ctx->num_args()) report_error("argument not found");
      |                                    ~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:675:27: note: 'void fmt::v11::report_error(const char*)' declared here
  675 | FMT_NORETURN FMT_API void report_error(const char* message);
      |                           ^~~~~~~~~~~~
```

Now, the error could be better. We don't know, for instance, _which_ argument is missing. And a lot of the context here isn't particularly helpful. Compare this to, for instance, the equivalent Rust program — which would fail with:

```rust
error: 1 positional argument in format string, but no arguments were given
 --> src/main.rs:2:17
  |
2 |     println!("x={}");
  |                 ^^
```

But the point is that we _do_ get a compile error and that compile error _does_ have information which helps us diagnose the problem.

At least, that was the error we got from gcc 13.3. What about the error we get from gcc 14.2? It looks [very different](https://godbolt.org/z/bvfchvP33):

```
<source>: In function 'int main()':
<source>:6:6: error: call to consteval function '<lambda closure object>main()::<lambda()>().main()::<lambda()>()' is not a constant expression
    4 |     []{
      |     ~~~
    5 |         fmt::print("x={}");
      |         ~~~~~~~~~~~~~~~~~~~
    6 |     }();
      |     ~^~
<source>:6:6: error: 'main()::<lambda()>' called in a constant expression
<source>:4:5: note: 'main()::<lambda()>' is not usable as a 'constexpr' function because:
    4 |     []{
      |     ^
<source>:5:19: error: call to non-'constexpr' function 'void fmt::v11::print(format_string<T ...>, T&& ...) [with T = {}; format_string<T ...> = fstring<>]'
    5 |         fmt::print("x={}");
      |         ~~~~~~~~~~^~~~~~~~
In file included from /opt/compiler-explorer/libs/fmt/trunk/include/fmt/format.h:41,
                 from <source>:1:
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:2936:17: note: 'void fmt::v11::print(format_string<T ...>, T&& ...) [with T = {}; format_string<T ...> = fstring<>]' declared here
 2936 | FMT_INLINE void print(format_string<T...> fmt, T&&... args) {
      |                 ^~~~~
<source>:5:19: note: 'main()::<lambda()>' was promoted to an immediate function because its body contains an immediate-escalating expression 'fmt::v11::fstring<>("x={}")'
    5 |         fmt::print("x={}");
      |         ~~~~~~~~~~^~~~~~~~
```

Now the only information we get is that the call to `fmt::print` is bad. We no longer have a diagnostic pointing to the line which at least had the call `report_error("argument not found")`. The former wasn't an amazing error, but at least we had a hint. We don't even have a hint anymore.

What happened?

## Some Background

Let's take a step back and consider a bunch of background for what the issue at hand actually is.

> If you want to skip all this background, you can [skip ahead](#how-does-fmt-type-check).
{:.prompt-info}

### Value-Based vs Type-Based Reflection

Several years ago, one of the discussions in the C++ community was around Reflection. In particular, what should the broad shape of the Reflection API be: should taking the reflection of some C++ source construct produce a unique _type_ or should it produce a unique _value_? That is:

```cpp
struct F { int x; float y; };

// Type
using Refl = reflexpr(F);
using Members = get_data_members_t<Refl>;

// Value
auto refl = reflexpr(F);
auto members = get_data_members(refl);
```

The Reflection TS was type-based (and came from [P0194](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0194r6.html)), and there were suggestions for both heterogeneous ([P0590](https://wg21.link/p0598)) and homogeneous ([P0598](https://wg21.link/p0598)) value designs (also called "type-rich" and "monotype," respectively), with a clear push towards homogeneous values ([P0425](https://wg21.link/p0425)). This eventually led to [P1240](https://wg21.link/p1240) which led to the current Reflection design on pace for C++26 ([P2996](https://wg21.link/p2996)).

However, along the way, there was a lot of work that needed to be done to support the homogeneous value design that we wanted for reflection. That led to `consteval` functions, `constexpr` allocation, `std::is_constant_evaluated()` (and later `if consteval`), etc.

Now, the promise of homogeneous-value-based reflection is that writing reflection code is a lot like writing normal code. And a lot of that promise _has_ panned out. Having seen, and written, a lot of reflection examples, I think this was the right design.

### Testing value-based reflection

But a few years ago, it wasn't clear to me if it was even viable. In early 2022, in the middle of some debates at the time of whether we should stick with value-based reflection or go back to the type-based model from the TS, it occurred to me that the promise of being able to just use ranges code with reflection might not be able to be fulfilled. The example I worked through in [P2564](https://wg21.link/p2564) was:

```cpp
namespace std::meta {
    struct info { int value; };

    consteval auto is_invalid(info i) -> bool {
        // we do not tolerate the cult of even here
        return i.value % 2 == 0;
    }
}

constexpr std::meta::info types[] = {1, 3, 5};
```

I don't think there was a suitable implementation available that supported both reflection and the `consteval` rules to work through this experiment, so I came up with this very, very loose approximation. Now the question was: we have `std::ranges::none_of`, is it possible for me to use that algorithm to verify that none of my `types` are `std::meta::is_invalid`? At the time, the answer was:

```cpp
// ❌ ill-formed
static_assert(std::ranges::none_of(types, std::meta::is_invalid));

// ❌ ill-formed
static_assert(std::ranges::none_of(
    types,
    [](std::meta::info i) { return std::meta::is_invalid(i); }
));

// ❌ ill-formed
static_assert(std::ranges::none_of(
    types,
    [](std::meta::info i) consteval { return std::meta::is_invalid(i); }
));

// ❌ ill-formed
static_assert(std::ranges::none_of(
    types,
    +[](std::meta::info i) consteval { return std::meta::is_invalid(i); }
));

// ✅ ok
consteval auto all_valid1() -> bool {
    return std::ranges::none_of(types, std::meta::is_invalid);
}
static_assert(all_valid1());

// ❌ ill-formed
consteval auto all_valid2() -> bool {
    return std::ranges::none_of(
        types,
        [](std::meta::info i) { return std::meta::is_invalid(i); }
    );
}
static_assert(all_valid2());

// ❌ ill-formed
consteval auto all_valid3() -> bool {
    return std::ranges::none_of(
        types,
        [](std::meta::info i) consteval { return std::meta::is_invalid(i); }
    );
}
static_assert(all_valid3());
```

That wasn't very encouraging. If even the simplest example doesn't even work except in very narrow circumstances...

### `consteval` shouldn't be a color

The problem was that `ranges::none_of` was `constexpr` — but it _sometimes_ needed to be `consteval`. It would be pretty bad if the solution to this problem was having to develop a parallel set of `consteval` algorithms in addition to our existing `constexpr` ones. That would make a mockery of the usability argument for value-based reflection.

Instead of making `consteval` a [color](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) in this way, it was important to make it so that `ranges::none_of` could _still work_ if the predicate were `consteval`.

Let's take a look real quick at a representative implementation of `none_of`:

```cpp
template <ranges::input_range R, class Pred>
constexpr auto ranges::none_of(R&& r, Pred pred) -> bool {
    auto first = ranges::begin(r);
    auto last = ranges::end(r);
    for (; first != last; ++first) {
        if (pred(*first)) {
            return false;
        }
    }
    return true;
}
```
{: data-line="6" .line-numbers }

The status quo was that if `pred` were a call to a `consteval` function (whether it's a function pointer or a function object with a `consteval operator()`, doesn't matter), then that expression _had_ to be a constant expression. Here, `pred(*first)` would have to be constant. But it _cannot_ be. So the call failed.

> Obligatory pedantic aside: Well, I mean, sure — your iterator could have an `operator*()` that reads no state at all and just returns `42`. In that case, this would work just fine. But most iterators are actually at least a _little bit_ more interesting and useful than that.
{:.prompt-info }

But what if instead of failing, we just... tried something else. For _that particular_ specialization of `none_of`, what if we changed it to look like this:

```cpp
template <ranges::input_range R, class Pred>
consteval auto ranges::none_of(R&& r, Pred pred) -> bool {
    auto first = ranges::begin(r);
    auto last = ranges::end(r);
    for (; first != last; ++first) {
        if (pred(*first)) {
            return false;
        }
    }
    return true;
}
```
{: data-line="2,6" .line-numbers }

Now that `none_of` is itself `consteval`, the expression `pred(*first)` is what's called an _immediate function context_, so it no longer has to itself be a constant. Just the call to `none_of` has to be.

> It's worth taking an aside to explain what's going on. The goal of `consteval` functions is to be able to ensure that they exist _only_ at compile time. You could just say that all calls to `consteval` functions have to be constant. But that ends up being overwhelmingly limiting, because you could not so much as even call another function:
> ```cpp
> consteval int square(int x) { return x*x; }
>
> consteval int call_square(int x) {
>    return square(x);
> }
> ```
> {: data-line="4" .line-numbers}
> The call `square(x)` isn't constant, `x` is a function parameter. But _because_ `call_square` is `consteval`, we already know that we only exist at compile time. So we don't need that same strictness in the body. We will already be enforcing that `call_square(x)` is constant — and that is sufficient. As a result, if you are in a context in which you already know is separately enforcing or ensuring compile time (whether inside of a `consteval` function or in an `if consteval`), we have more relaxed rules. It takes a while to reason through, but it's a pretty sensible layering.
{:.prompt-info}

That was the gist of my `consteval` propagation paper: if a `constexpr` function template contains a call to a `consteval` function that isn't constant, just pretend that we were always a `consteval` function template to begin with. It gets _escalated_ to a `consteval` function template. This escalation can bubble arbitrarily many layers up — doesn't matter how many `constexpr` function templates exist between the outer call and the inner `consteval` expression.

### The `constexpr` rules are very complicated

Before I get back to the main point of this blog, it's worth taking an aside on the `constexpr` rules. In C++11, the rules were very simple. [\[expr.const\]](https://timsong-cpp.github.io/cppwp/n3337/expr.const) at the time was just five paragraphs. There was very little you could do during constant evaluation, and `constexpr` functions were _highly_ limited. They could contain [just a single `return` statement](https://timsong-cpp.github.io/cppwp/n3337/dcl.constexpr#3.4.6).

As C++26 is getting ready to ship, the rules are _much_ more complicated. [\[expr.const\]](https://eel.is/c++draft/expr.const) is now 29 paragraphs, with more complicated wording. And that's before Reflection adds some more.

It's worth asking: is this bad?

I would say no. While the rules themselves are more complicated and harder to understand (I even occasionally struggle with rules that I myself added), the consequence of having them is that actually fewer people have to even think about what the rules are. At a first approximation, nobody cares what the `constexpr` rules actually are. You just write your code, and if it works during constant evaluation, you just move on with your life. You're not going to stop to think about _why_ it worked. It's only when it _doesn't_ work that you have to take the time to understand why it _didn't_.

That's why I think it's valuable to constantly push to widen what's allowed during constant evaluation. That's why Hana Dusíková [writes](https://wg21.link/p3367) [all](https://wg21.link/p3372) [these](https://wg21.link/p3378) [papers](https://wg21.link/p3533) [so](https://wg21.link/p3037]) [that](https://wg21.link/p3125) [things](https://wg21.link/p3068) [just](https://wg21.link/p3349r0) [work](https://wg21.link/p3309).

## How does `{fmt}` type check?

Okay back to the original issue. How does `{fmt}` actually do compile-time type checking? In [P2216R0](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2020/p2216r0.html#checks), Victor Zverovich simply stated that we should do this because:

> we’ve found that users expect errors in literal format strings to be diagnosed at compile time by default.

But without suggesting an approach for how to make it happen. By [R1](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2020/p2216r1.html#checks), he'd figured out how to make it work. The gist of the solution is this (I'm going to drop the `charT` template parameter and assume that `char` is the only character type):

```cpp
template <class... Args>
struct basic_format_string {
    string_view sv;

    template <class T>
        requires std::convertible_to<T const&, string_view>
    consteval basic_format_string(T const& s)
        : sv(s)
    {
        // Report a compile-time error if s is not a format string for {Args...}
    }
};

template <class... Args>
using format_string = basic_format_string<type_identity_t<Args>...>;

template <class... Args>
auto format(format_string<Args...> fmt, Args const&... args) -> string;
```
{: data-line="7" .line-numbers }

The key is that `consteval`. When you write `format("{:d}", "I am not a number")`, we have to construct the `format_string<char const[18]>`. (the `Args...` are wrapped in `type_identity_t` so that this one is not independently deduced). The construction `format_string<char const[18]>("{:d}")` has to be a constant expression — this is what `consteval` enforces. And once we're in the body of the constructor, we can just parse the format string and do some non-`constexpr`-friendly thing when we find an invalid format specifier (like `d` for a string). In this case, `{fmt}` calls a non-`constexpr` function.

This is very clever.

It's also not _quite_ how we want this to work, but more on this later.

## When `consteval` propagation goes wrong?

The `consteval` propagation that we adopted for C++23 is pretty much always want you want to happen. It's one of those really nice language extensions which takes code from ill-formed to valid-and-does-what-you-want, without any syntax changes necessary. That's kind of the dream.

With all that background out of the way, let's revisit my original example:

```cpp
#include <fmt/format.h>

int main() {
    []{
        fmt::print("x={}");
    }();
}
```

This works the same way I just described. This time, we're initializing `format_string<>` from `"x={}"`. This isn't going to work, because our format string has a replacement field but we have no arguments to replace. That call won't be a constant expression, as desired. So we're good right?

*Except* the specific way in which this doesn't work is that the initialization of `format_string<>` from `"x={}"` is a call to a `consteval` function that isn't a constant expression. Earlier, that would just be an error. But now what ends up happening is that a constant evaluation failure kind of just means: try harder. So we keep widening our lens, to see if marking more things `consteval` can solve the problem. Earlier, I just mentioned `constexpr` function templates — but lambdas can be `consteval` too. So, in this case, that immediately-invoked lambda is escalated to `consteval`. And escalation stops there because `main` is a non-`constexpr` function.

But now a very strange thing happens. When we evaluate the now-`consteval` lambda, the call to which has to be a constant expression, we run into a _different_ problem: `fmt::print` isn't `constexpr`. And that's the error that gcc is currently reporting:

1. The call to the (now-)`consteval` lambda isn't a constant expression, because
2. We're calling the non-`constexpr` function `fmt::print("x={}")`.
3. Note: the lambda was promoted to `consteval` because of the immediate-escalating expression `format_string<>("x={}")` (which in `{fmt}` is actually spelled `fmt::v11::fstring<>`).

> The difference between [gcc 13.3 and gcc 14.2](https://godbolt.org/z/bvfchvP33) is that the latter now implemented `consteval` propagation, while the former did not.
{:.prompt-info}

Being told that `fmt::print` isn't a `constexpr` function is a strange thing to see in an error message when of course you know that and you are not even trying to do any compile-time printing! And then we lose all information about _why_ the format string initialization wasn't constant.

Importantly, `consteval` propagation does not ever take previously valid code and make it invalid. It only takes previously invalid code and make it valid. However, in this case, it took previously invalid code which remains invalid — but the diagnostic quality got significantly worse.

Can this situation be improved?

## Where to go from here?

It would be nice if we could do better: have both the benefits of `consteval` propagation and also the benefits of having type-checking errors that are at least possible to make sense of.

Initially, my first reaction is that we could go a little narrower on the `consteval` propagation front. After all, the cause of our failure is:

```cpp
/opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:2438:48: error: call to non-'constexpr' function 'void fmt::v11::report_error(const char*)'
 2438 |     if (arg_id >= ctx->num_args()) report_error("argument not found");
      |                                    ~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~
```

`report_error()` is a non-`constexpr` function. It's not going to magically _become_ a `constexpr` function by making more things `consteval`. This is doomed to failure. Perhaps certain kinds of constant evaluation failure do not propagate.

However, before we explore this too deeply, it's worth considering the future of how `{fmt}` might report failures. Currently, this is by invoking non-`constexpr` functions. But now that you can throw exceptions at compile-time (thanks Hana), it's possible that `{fmt}` might change to do so in the future. Using Hana's [fork](https://compiler-explorer.com/z/WcxfxfePP):

```cpp
struct format_string {
    consteval format_string(char const* sv) {
        // just check that it doesn't contain a replacement field
        while (*sv) {
            if (sv[0] == '{' and sv[1] != '{') {
                char const* msg = "no replacement fields allowed";
                throw exception(msg);
            }
            ++sv;
        }
    }
};
```

This example deliberately is indirectly `throw`ing the message, since we might actually be constructing the message from contents of the format string. And you can still see the full contents of the message in the diagnostic

```cpp
<source>:14:17: note: unhandled exception: no replacement fields allowed
   14 |                 throw exception(msg);
      |                 ^
```

I bring up exception because while invoking a non-`constexpr` function is just never going to be constant if you widen out, `throw`ing an exception might actually _become constant_ if you do so.

Consider:

```cpp
consteval auto throw_up() -> void {
  throw std::meta::exception(...);
}

template <class F>
constexpr auto attempt_to(F f) -> bool {
  try {
    f();
    return false;
  } catch (...) {
    return true;
  }
}

static_assert(attempt_to([]{ throw_up(); }));
```

Currently, `throw_up()` is immediate-escalating, causing the appropriate specialization of `attempt_to` to become `consteval`. And at that point, that specialization is actually a constant expression (that returns `true`). If we did not allow that exception-throwing to escalate, then the call would become ill-formed. Which suggests that exception-throwing _must_ be allowed to escalate — which means that even if we prune the escalation of non-`constexpr` function calls, the exception throwing will remain, and a hypothetical future implementation of `{fmt}` that diagnoses invalid format strings by throwing will still have the same diagnostic problems.

## An alternate approach

Ultimately, in Victor's original draft, he's hinting at the real issue. He wrote:

> Without a language or implementation support it’s only possible to emulate the desired behavior by passing format strings wrapped in a `consteval` function, a user-defined literal, a macro or as a template parameter, for example:
>
> ```cpp
> std::string s = std::format(std::static_string("{:d}"), "I am not a number");
> ```

In particular, what we _really_ want to do is that this:

```cpp
std::string s = std::format("{:d}", "I am not a number");
```

Evaluates as this:

```cpp
constexpr auto __fmt = std::format_string<char const[18]>("{:d}");
std::string s = std::format(__fmt, "I am not a number");
```

The `consteval` constructor almost gets us there. Or, rather, it definitely gets us there from the perspective of wanting to always make invalid format strings into compile errors. But it doesn't quite get us there to actually provide good diagnostics in case of that failure.

> My bad.
{:.prompt-info}

But the `constexpr` variable rewrite _does_. Because `consteval` escalation can only widen up to the point of the constant evaluation — and `constexpr` variable initialization is its own constant evaluation. If we rewrite our example to [explicitly do that](https://godbolt.org/z/6ac3eqKK1):

```cpp
#include <fmt/format.h>

int main() {
    []{
        constexpr fmt::format_string<> __fmt = "x={}";
        fmt::print(__fmt);
    }();
}
```

Then we see that with both gcc 13.3 and gcc 14.2, we get the same error — which points directly to the issue:

```cpp
opt/compiler-explorer/libs/fmt/trunk/include/fmt/base.h:2438:48: error: call to non-'constexpr' function 'void fmt::v11::report_error(const char*)'
 2438 |     if (arg_id >= ctx->num_args()) report_error("argument not found");
      |                                    ~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~
```

