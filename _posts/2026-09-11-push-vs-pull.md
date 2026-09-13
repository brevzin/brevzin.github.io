---
layout: post
title: "Push-based vs Pull-based Customization"
category: c++
tags:
 - c++
 - c++29
 - reflection
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

> Note that the actual spelling of the attribute as `derive<Debug>` as opposed to `print` or something is not essential. I was just trying to be cute. There is no significance to the template there.
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

Now, for the vast majority of types, that approach works great. The problem is, that's not guaranteed for _all_ types. As I pointed out in the original post, because we just added a partial specialization, if any other partial specialization matches (such as the range one), then we just have an ambiguous specialization. Even though it's arguably very clear from user-intent that adding the annotation means they want _this_ behavior, there's no way in the language to specify that today.

> Nor would I really know how to come up with a way to specify it tomorrow.
{:.prompt-info}

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
    // do a bunch of work building up fmt_body that isn't
    // strictly relevant here, and then eventually ...
    queue_injection(^^std, ^^{
        template <>
        struct formatter<\(ty)> {
            constexpr auto parse(auto& ctx) {
                return ctx.begin();
            }

            auto format(\(ty) const& object, auto& ctx) const {
                \(fmt_body);
            }
        };
    });
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
            // the outer parens here are actually load-bearing
            return (((Self&&)self).[: \(persisted.data())[I] :]);
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

auto main() -> int {
    // ...
}
```
{: data-line="14"  }

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

But in short, for every template, there is a point (or set of points) at which that template is allowed to be instantiated. In my implementation of `wide_result<T>` above, instantiating a particular specialization would invoke `inject_structured_bindings`, which would then inject the necessary customization points for `tuple_size`, `tuple_element`, and `get`. But that only happens _when we instantiate_ `wide_result<T>`. The expression `tuple_size_v<X> == 2` doesn't actually require instantiating `X`, so it doesn't, so our `consteval` block doesn't get evaluated, so our customization points don't get injected, and the assertion fails.

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
{: data-line="19"  }

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

## Push-Me, Pull-Me I

In order to inject that partial specialization properly, we need to be able to do so _earlier_. We can't have a `consteval` block within our class template, since that's not going to be evaluated yet. It seems too complicated to try to come up with rules for when a `consteval` block means "when a class is instantiated" and when it means "at the point of template definition." So we really want a signal _outside_ of the body to tell us to do this. And we have one: an annotation.

```cpp
template <class T>
class [[=inject_bindings]] wide_result {
    // ...
};
```

No cute name this time. But what we do still have this time is a callback for when the entity the annotation is attached to gets completed. Except that this time, instead of type completion it'll be template definition. So something like this:

```cpp
struct inject_bindings_t {
    consteval auto on_template_defined(std::meta::info tmpl) const -> void {
        // ...
    }
};

inline constexpr inject_bindings_t inject_bindings{};
```

This basically behaves as if we'd written:

```cpp
template <class T>
class wide_result {
    // ...
};

consteval {
    inject_bindings.on_template_defined(^^wide_result);
}
```

Now, we just need to inject a partial specialization of `tuple_size` that matches all specializations `wide_result`. Except all we have is... a class template. How do we know how to do that?

The general C++ approach up to now is to just match a variadic class template. That would look like:

```cpp
struct inject_bindings_t {
    consteval auto on_template_defined(std::meta::info tmpl) const -> void {
        queue_injection(^^std, ^^{
            template <class... Ts>
            struct tuple_size<\(tmpl)<Ts...>> {
                // ...
            };
        });

        // similar for tuple_element
    }
};
```

This certainly works for `wide_result`, which takes some number of template parameters (one) that are all types. But it's not a general solution. It wouldn't work for types with constant template parameters or template template parameters (or, now, concept template parameters or variable template parameters). And the whole point of this point is that I do want a general solution. What would a general solution look like?

This is what [universal template parameters](https://wg21.link/p2989) are for. While there are many motivating use-cases for this feature (see the paper), this one is particularly annoying since it's the simplest possible usage: we don't even care here what the template parameters actually _are_ — we will never attempt to look at them because we care only about the overall type and that it has this specific pattern. With the paper, what we'd inject would be:

```cpp
struct inject_bindings_t {
    consteval auto on_template_defined(std::meta::info tmpl) const -> void {
        queue_injection(^^std, ^^{
            template <universal template... Ts>
            struct tuple_size<\(tmpl)<Ts...>> {
                // ...
            };
        });

        // similar for tuple_element
    }
};
```
{: data-line="4" }

That's a general solution that works for all class templates. The other approach to a general solution would be try to come up with a way to inject exactly the template-head for the specific template. That is:

```cpp
// our first not-quite-solution: only works for type parameters
template <class... Ts>
struct tuple_size<wide_result<Ts...>> { ... };

// our second solution: works for all class templates
template <universal template... Ts>
struct tuple_size<wide_result<Ts...>> { ... };

// third solution: write exactly the template-head
template <class T>
struct tuple_size<wide_result<T>> { ... };
```

In order to do that, we'd need some helpers to produce the two different parts of the signature here. We'd need a way to produce the token sequence `^^{ class T }` and a way to produce the token sequence `^^{ T }`. This would probably need to have some way of allowing us to provide a prefix for the parameter names themselves, since we need to ensure they don't clash, and the names themselves don't matter. Perhaps the signature of this function would be something like:

```cpp
struct template_head_result {
    std::meta::token_sequence head;
    std::meta::token_sequence args;
};

consteval auto template_head_of(std::meta::info tmpl, std::string_view prefix)
    -> template_head_result;
```

So that our usage here would be:


```cpp
struct inject_bindings_t {
    consteval auto on_template_defined(std::meta::info tmpl) const -> void {
        auto [head, args] = template_head_of(tmpl, "p");

        queue_injection(^^std, ^^{
            template <\(head)>
            struct tuple_size<\(tmpl)<\(args)>> {
                // ...
            };
        });

        // similar for tuple_element
    }
};
```
{: data-line="3,6-7" }

Note that template heads can be arbitrarily complicated. They can have constrained declarations, they can re-use names. For instance, `std::integral_constant` is:

```
template <class T, T v>
struct integral_constant;
```

So `template_head_of(^^integral_constant, "p").head` would have to produce something like `^^{ class p0, p0 p1 }` and definitely not `^^T{ class p0, T p1 }`.

> I'm sure if I knew anything about programming language theory or lambda calculus, I'd talk about α-conversion or something.
{:.prompt-info}

So alright, those are our three options (just use types, universal template parameters, and dedicated reflection functions to synthesize the correct template-head) to properly _push_ the right specialization. But once we have that shape, what do we do next?

## Push-Me, Pull-Me II

In my initial implementation of injecting structured bindings, I passed a vector of reflections representing non-static data members into a function that did all the injections for me. That can't really work if we're driving all of this from an annotation, since the annotation lives outside of the class — before the non-static data members are declared. That means we'll have to split the work: _push_ the right specializations, but have those specializations _pull_ the data back out.

That is, our usage will look something like this:

```cpp
template <class T>
class [[=inject_bindings]] wide_result { // <== push-me
    T hi;
    T lo;

public:
    constexpr wide_result(T hi, T lo) : hi(hi), lo(lo) { }

    static constexpr info tuple_elements[] = {^^hi, ^^lo}; // <== pull-me
};
```
{: data-line="2,9" }

The annotation injects all the pieces we need, the `static constexpr` data member is... the parameter for that annotation. It's a little unsatisfactory that these two are split so far apart. Then again, `tuple_elements` here could conceivably just default to `nonstatic_data_members_of(^^C)`, so perhaps that's not that big a deal.

Before, pull-based customization was problematic due to having the potential for ambiguous specializations. But once we push the correct specialization out, that's no longer a problem, and pulling data is fine.

Concretely, we can inject this (note that this still just injects specializations assuming all-type parameters):

```cpp
template <class T, template <class...> class Z>
concept specializes = has_template_arguments(remove_cvref(^^T))
                    and template_of(remove_cvref(^^T)) == ^^Z;

struct inject_bindings_t {
    consteval auto on_template_defined(std::meta::info tmpl) const -> void {
        queue_injection(^^std, ^^{
            template <class... Ts>
            struct tuple_size<\(tmpl)<Ts...>>
                : integral_constant<size_t, size(\(tmpl)<Ts...>::tuple_elements)>
            { };

            template <size_t I, class... Ts>
            struct tuple_element<I, \(tmpl)<Ts...>> {
                using type = [: type_of(\(tmpl)<Ts...>::tuple_elements[I]) :];
            };
        });

        queue_injection(parent_of(tmpl), ^^{
            template <size_t I, ::lib::specializes<\(tmpl)> Self>
            constexpr auto get(Self&& self) -> decltype(auto) {
                return (((Self&&)self).[: self.tuple_elements[I] :]);
            }
        });
    }
};
```

The fully qualified `::lib::specializes` is just because I'm assuming this annotation is actually in namespace `lib`. And if you're wondering how we can splice `self.tuple_elements[I]` inside of `get`, check out my post about the [constexpr array size problem]({% post_url 2020-02-05-constexpr-array-size %}).

Now that implementation [works](https://compiler-explorer.com/z/T9EcMsacf), even if I put the `static_assert` before I instantiate `wide_result`.

## There's Always Another Level

Now, even with the above solution, it's still not quite satisfactory to me. First, there's the shape of the specialization that I've already mentioned — how we really need either universal template parameters or a mechanism to generate the correct template head for a given template. But on top of that, I'm not thrilled that we have to inject `get` into namespace scope — ideally I think we would inject it into `wide_result`, so that we're not polluting the namespace.

But there's a bigger issue here, because there's always a bigger issue.

Consider classes of this shape:

```cpp
template <class T>
struct Outer {
    struct Inner {
        // ...
    };
};
```

If I want to push a specialization for some trait (whether `formatter` or `tuple_size` or some other customization point), the spelling I would end up producing, even with an oracle that would give me the correct spelling, is:

```cpp
template <class T>
struct TRAIT<Outer<T>::Inner> {
    // ...
};
```

And... that doesn't work. That's never going to match anything, because that pattern is a non-deduced context. On the one hand, there are good reasons for that in general — since if `Inner` were, rather than its own type, actually `using Inner = int;`, then obviously you could not deduce `T` from that. But on the other hand, if `Inner` is _not_ an alias, then `T` is very clearly deducible.

This is already a known problem in this space, which is why some libraries try to avoid nested types in these contexts — you can always just restructure your code to look like this:

```cpp
template <class T>
struct Inner {
    // ...
};

template <class T>
struct Outer {
    // ...
};
```

It's just... annoying to have to do so, purely when considering locality. I might want `Inner` to actually be a nested class of `Outer` for any number of reasons, so having to put it outside of `Outer` to work around a language limitation is always irritating. Perhaps this would be a reason to reconsider that rule, but otherwise because `Outer<T>::Inner` is non-deducible, that means that such types can _only_ be customized pull-based — never push-based.

## Next Steps

I'm going to keep trying things out in this space and seeing what works. But part of my motivation with this blog post is also that I realize that while I have this implementation on compiler explorer, I haven't done much in the way of advertising its existence. I hope to have an updated token sequence injection paper in the September mailing with links to further examples. I've already have a few in this post already, but probably some of the more interesting ones I've been working through are:

* [type erasure](https://compiler-explorer.com/z/5v1dvvbvq)
* [formatting](https://compiler-explorer.com/z/Ehxrb3z13)
* [iterator interface](https://compiler-explorer.com/z/en5bbrYW1), some early experimentation with an iterator library that is "fill in the rest of the owl for me"
* the [final implementation](https://compiler-explorer.com/z/T9EcMsacf) of the push/pull based structured bindings implementation

I'm curious what you all will come up with: what you will try to do that just works, what you will try to do that fails but should work, what you want to do that we need other (or differently shaped) tools for. Let's do this!