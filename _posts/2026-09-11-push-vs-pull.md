---
layout: post
title: "Push-based vs Pull-based Customization"
category: c++
tags:
 - c++
 - c++29
pubdraft: yes
---

Almost two years ago now, I wrote the post [Rust Attributes vs C++ Annotations]({% post_url 2024-09-30-annotations %}). That post, I walked through how in standard C++26 we could get this code:

```cpp
struct [[=derive<Debug>]] Point {
    int x;
    int y;
};
```

To have similar behavior and effect to this standard Rust code:

```rust
#[derive(Debug)]
struct Point {
    x: i32,
    y: i32,
}
```

> Note that the actual spelling of the attribute as `derive<Debug>` as oppose to `print` or something is not essential. I was just trying to be cute. There is no significance to the template there.
{:.prompt-info}

This blog post will walk through different approaches to living up to that goal and how they... don't quite.

## Pull-based annotations

The original approach there was that we provide a partial specialization of `formatter` that _pulls_ the annotation and internally does all the right things — walks through the data members, etc.:

```cpp
template <class T> requires (has_annotation(^^T, derive<Debug>))
struct std::formatter<T> {
    // ...
};
```

Importantly, just _similar_ behavior. Now, for the vast majority of types, that approach works great. The problem is, that's not guaranteed for _all_ types. As I pointed out in the original post, because we just added a partial specialization, if any other partial specialization matches (such as the range one), then we just have an ambiguous specialization. Even though it's arguably very clear from user-intent that adding the annotation means they want _this_ behavior, there's no way in the language to specify that.

That's pretty disappointing. Works most of the time is pretty good, but I'd really want a solution that works all of the time.

## Push-based annotations

I got to deliver a [keynote](https://youtu.be/DZTkT1Cq_aY?si=CSbPSx6T4JQSwW_N) at CppNow this year, where I talked about what I think a good direction will be for reflection-related programming after C++26. I presented an idea for solving this particular problem at [54:07](https://youtu.be/DZTkT1Cq_aY?t=3247), where I suggested this approach (again with an unnecessary cute spelling of the annotation):

```cpp
template <class F>
struct derive {
    F f;

    consteval auto on_complete(std::meta::info r) const -> void {
        f(r);
    }
};

inline constexpr auto Debug = [](std::meta::info ty){
    // inject a specialization of formatter<\(ty)>
};

struct [[=derive(Debug)]] Point {
    int x;
    int y;
};
```

The actual specifics of implementing `Debug` aren't essential here, but you can see an implementation on [compiler explorer](https://compiler-explorer.com/z/89oK3qx5r). The idea is that `on_complete` on an annotation gets invoked when the class it's on becomes complete, and the implementation then injects the appropriate specialization, which it builds up using token sequences.

Alternatively, using the approach I also went through at [CppCon](https://youtu.be/ZX_z6wzEOG0?t=2487), where we have `derive_formatter<T>` that specifically does this debug formatting that I want, the minimal use of token sequences would be to implement `Debug` above like so:

```cpp
inline constexpr auto Debug = [](std::meta::info ty){
    queue_injection(^^std, ^^{
        template <>
        struct formatter<\(ty)> : debug_formatter<\(ty)> { };
    });
};
```

And, as you can see in the linked implementation, this works. On both classes and class templates:

```cpp
struct [[=derive(N::Debug)]] Config {
    std::string name;
    int amount;
};

template <class T>
struct [[=derive(N::Debug)]] Widget {
    T thing;
};
```

I can print all of these things in the way that I expect. Which is awesome! And now that we're injecting an _explicit_ specialization instead of a partial specialization, this is a solution that definitely works for all types.

Right?

*Right?!*

## Injecting Structured Bindings

Let's take a step away from formatting for a minute. There do exist other problems after all. I want to talk about structured bindings. The problem with structured bindings today is that when you need to write customization points for them, it's a real pain — you have to implement three different customization (`tuple_size`, `tuple_element`, and `get`) which really are all driven from the same source.

So I thought I'd experiment with injecting those three customizations from a single source. That's mostly [pretty straightforward](https://compiler-explorer.com/z/naEnrx96e):

```cpp
#include <meta>
#include <print>

consteval auto inject_structured_bindings(std::vector<std::meta::info> elems)
    -> void
{
    std::meta::info ty = parent_of(*elems.begin());

    // tuple_size
    queue_injection(^^std, ^^{
        template <>
        struct tuple_size<\(ty)>
        : integral_constant<size_t, \(elems.size())>
        { };
    });

    // tuple elements
    for (size_t i = 0; i < elems.size(); ++i) {
        queue_injection(^^std, ^^{
            template <>
            struct tuple_element<\(i), \(ty)> {
                using type = \(type_of(elems[i]));
            };
        });
    }

    // get is local
    auto persisted = std::define_static_array(elems);
    queue_injection(^^{
        template <size_t I, class Self>
        constexpr auto get(this Self&& self) -> decltype(auto) {
            return ((Self&&)self).[: \(persisted.data())[I] :];
        }
    });
}

template <class T>
class wide_result {
    T hi;
    T lo;

public:
    constexpr wide_result(T hi, T lo) : hi(hi), lo(lo) { }

    consteval {
        inject_structured_bindings({^^hi, ^^lo});
    }
};

auto main() -> int {
    auto [hi, lo] = wide_result<uint64_t>(123, 456);
    std::println("hi={}, lo={}", hi, lo); // prints hi=123, lo=456
}
```

In that function, I'm injecting one explicit specialization of `tuple_size`, `N` explicit specializations of `tuple_elements` (this could conceivably instead be one partial specialization), and then a _local_ function template `get`. The only awkward-ness in the implementation is that `persisted` variable — `get<I>` needs to produce the `I`th binding, but `I` isn't known until we instantiate `get`, whereas we need to inject something _now_. The interesting thing about code injection is trying to reason about things that are constant at different times during compilation. There might be a better approach to this particular sub-problem, I still have to think about it.

In any case, this does work, as you can see.

At least until I went ahead and tried to add a `static_assert`:

```cpp
template <class T>
class wide_result {
    T hi;
    T lo;

public:
    constexpr wide_result(T hi, T lo) : hi(hi), lo(lo) { }

    consteval {
        inject_structured_bindings({^^hi, ^^lo});
    }
};

static_assert(std::tuple_size_v<wide_result<uint64_t>> == 2);
```
{: data-line="14" .line-numbers }

You may be surprised to learn, especially after the previous program worked, that adding this assertion [breaks the program](https://compiler-explorer.com/z/n8rr8WTnK). The error message is:

```cpp
/cefs/48/486ef4e598174af0b0b3e1a2_clang-barry-clang-trunk-20260910/bin/../include/c++/v1/__tuple/tuple_size.h:63:40: error: implicit instantiation of undefined template 'std::tuple_size<wide_result<unsigned long>>'
   63 | inline constexpr size_t tuple_size_v = tuple_size<_Tp>::value;
      |                                        ^
<source>:47:20: note: in instantiation of variable template specialization 'std::tuple_size_v<wide_result<unsigned long>>' requested here
   47 | static_assert(std::tuple_size_v<wide_result<uint64_t>> == 2);
      |                    ^
/cefs/48/486ef4e598174af0b0b3e1a2_clang-barry-clang-trunk-20260910/bin/../include/c++/v1/__tuple/tuple_size.h:27:8: note: template is declared here
   27 | struct tuple_size;
      |        ^
```

What do you mean undefined template `tuple_size<wide_result<uint64_t>>`. Didn't I define it? Didn't I _just show_ that it's defined?

## Point of Instantiation

Dan Katz's favorite part of the standard is [temp.point]: "Point of instantiation." The part of the standard that almost, but not quite, doesn't really describe anything about how templates actually work.

But in short, for every template, there is a point (or set of points) at which that template is instantiated. In my implementation of `wide_result<T>` above, instantiating a particular specialization would invoke `inject_structured_bindings`, which would then inject the necessary customization points for `tuple_size`, `tuple_element`, and `get`. But that only happens _when we instantiate_ `wide_result<T>`. The expression `tuple_size_v<X> == 2` doesn't actually require instantiating `X`, so it doesn't, so our `consteval` block doesn't get evaluated, so our customization points don't get injected, and the assertion fails.

> It's actually even worse than that, since if we had a `concept` that checked to see whether `wide_result<T>` had a `tuple_size`, and we checked that concept before we instantiated `wide_result<T>`, then that `concept`'s answer would change after we instantiated it. Which means our program is ill-formed, no diagnostic required.
{:.prompt-info}

However, if our `wide_result` specialization was _already_ instantiated, then the `consteval` block would have run, the injections would have occurred, and everything is actually... just fine:

```cpp
template <class T>
class wide_result {
    T hi;
    T lo;

public:
    constexpr wide_result(T hi, T lo) : hi(hi), lo(lo) { }

    consteval {
        inject_structured_bindings({^^hi, ^^lo});
    }
};

auto main() -> int {
    auto [hi, lo] = wide_result<uint64_t>(123, 456);
    std::println("hi={}, lo={}", hi, lo);
}

static_assert(std::tuple_size_v<wide_result<uint64_t>> == 2); // ok
```
{: data-line="19" .line-numbers }

Needless to say, this is very fragile!

> The same issue would occur in the push-based formatting example, when the annotation is applied to a template. If you check if a type `T` is `formattable` before `T` is instantiated, we wouldn't have injected the specialization yet, so we would observe a `false` result. This is less likely to be an issue with formatting _specifically_, where we're usually checking for formatting on an object we have in front of us (and thus the type is already instantiated) rather than just a type. But less likely doesn't mean never.
{:.prompt-info}

## What do we need to do?

Right now, the problem is that we're injecting this:

```cpp
template <class T>
class wide_result { /* ... */ };

// on instantiation of wide_result<u64>
namespace {
    template <>
    struct tuple_size<wide_result<u64>> {
        // ...
    };
}
```

One approach would be to some inject a partial specialization that matches specializations of `wide_result`. Like so:

```cpp
template <class T>
class wide_result { /* ... */ };

// immediately after the definition of wide_result<T>
namespace {
    template <class T>
        requires (has_template_arguments(^^T)
              and template_of(^^T) == ^^wide_result)
    struct tuple_size<T> {
        // ...
    };
}
```

But this is still a partial specialization, so we could run into exactly the same sort of issue with clashing specializations that the pull-based annotation model runs into. Since this is... precisely a pull-based specialization.

The only real approach is to inject precisely this:

```cpp
template <class T>
class wide_result { /* ... */ };

// immediately after the definition of wide_result<T>
namespace {
    template <class T>
    struct tuple_size<wide_result<T>> {
        // ...
    };
}
```

This is still a partial specialization, true, but it's going to be the most specialized possible one, so we don't have to deal with any other generic clashes.

But this leads to two questions:

* how, exactly, do we inject that specialization?
* and what, exactly, is it's definition?