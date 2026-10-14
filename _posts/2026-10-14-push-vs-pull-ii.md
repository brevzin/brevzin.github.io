---
layout: post
title: "Generating Operator Functions"
category: c++
series: push-vs-pull
tags:
 - c++
 - c++29
 - reflection
---

In a [previous post]({% post_url 2026-09-14-push-vs-pull %}), I discussed the differences between push-based and pull-based customization in the context of trying to implement support for formatting and structured bindings. For those problems, pull-based customization (adding an annotation to a type and having a partial class template specialization that looks for that annotation) works pretty well — until you suddenly run into ambiguities. So in some cases, you really want to inject an explicit specialization instead — which works until the you need to check the customization point before you actually instantiate the class. At that point, want to inject a partial specialization that matches the class template shape.

In [P4380R0](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2026/p4380r0.html#push-based-customization-iii), I showed an example that does full declaration cloning, so we can do the right thing for all class templates.

In this post, I wanted to walk through another customization example where a pull-based approach really falls apart and push-based customization is essential: generating operator functions.

## Bitmask operations for enums (P4313)

In [P4313](https://wg21.link/p4313), Iliya Guterman and Anthony Williams propose a library solution to a problem I've seen lots of people desire a good solution for: how to treat an enumeration type as a bitmask. Their proposal is that adding an annotation to an enum will give you all the relevant bit-masking operators. The lead example from the paper:

```cpp
enum class [[=std::bitmask_type]] Permission {
  None    = 0,
  Read    = 1 << 0,
  Write   = 1 << 1,
  Execute = 1 << 2,
};

int main () {
    // Combine permissions
    Permission user_perms = Permission::Read | Permission::Write | Permission::Execute;

    if ((user_perms & Permission::Read) == Permission::Read)
        std::cout << "Can read";

    Permission can_read_and_write = Permission::Read | Permission::Write;
    if ((user_perms & can_read_and_write) == can_read_and_write)
        std::cout << "Can read and write";
}
```

> Now, some people will argue that this is the wrong way to write bit masks, and you should instead have a regular enumeration (where `Permission::None == 0`, `Permission::Read == 1`, `Permission::Write == 2`, etc.) and simply use something like `BitMask<Permission>` here. For instance, Ben Deane talked about this in a couple of talks that I've seen of his recently. If you think this is the wrong way to write bitmasks and the proposal is a bad idea, that's fine, but I still think it makes for a good example to discuss.
{:.prompt-info}

The way this works is that the implementation adds operators in the global namespace that check for the presence of this annotation — a pull-based customization. The implementation in the paper [looks like this](https://godbolt.org/z/TahWzn4xd):

```cpp
namespace std {

inline constexpr struct BitmaskType {} bitmask_type;

template <typename T>
concept BitmaskTypeLike =
    std::is_enum_v<T>
    and (not annotations_of_with_type(^^T, ^^BitmaskType).empty());
} // std


template <std::BitmaskTypeLike T>
constexpr T operator|(T lhs, T rhs) {
  return static_cast<T>(std::to_underlying(lhs) | std::to_underlying(rhs));
}

template <std::BitmaskTypeLike T>
constexpr T operator&(T lhs, T rhs) {
  return static_cast<T>(std::to_underlying(lhs) & std::to_underlying(rhs));
}

// etc.
```

Pretty straightforward approach. It just has one serious problem: it doesn't work.

## Names and Where to Find Them

Name lookup in C++ is very complicated, but we have to talk about how it works. When you have an expression like `x | y` between two enums, we look for an `operator|` in two ways:

1. Regular unqualified lookup: start with our current scope and keep going outward until we find a function named `operator|`. Once we find any, stop, and collect all of them in that scope.
2. Argument-dependent lookup (ADL): look in all the associated namespace of the arguments for all functions named `operator|`.

Now, consider what happens if our `Permission`  enumeration is in a namespace like this:

```cpp
namespace N {
    enum class [[=std::bitmask_type]] Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };
}
```

The operators we need to find are in the global namespace, which isn't an associated namespace of `N::Permission` (or indeed, any enum in some other namespace). So we need regular unqualified lookup to find our operators. But in order for that to work, there have to be _no_ other operators between our use of `|` and the declaration of `operator|` in global scope where the operators are that we need to find it. Which is even more fragile than the ambiguity issues I was talking about with the class template specialization based customization.

[Consider](https://godbolt.org/z/E565bdj8a):

```cpp
namespace N {
    enum class [[=std::bitmask_type]] Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };
}

int main() {
    using enum N::Permission;
    auto x = Read | Write;                 // OK
    auto y = std::bit_or{}(Read, Write);   // error
}
```
{: data-line="12-13"  }

Why does line 12 work but not line 13? Because in our direct call to `Read | Write`, regular unqualified lookup goes straight to global scope, where we find the `operator|` we need to. But if we try to use `std::bit_or`, the call to `|` is written inside of `std`, and `std` has _lots_ of functions named` operator|` in it. So that's our candidate set — we never get to the global namespace.

This isn't specific to `std::bit_or` and friends either. Any `operator|` that's in our way will prevent [this](https://godbolt.org/z/abMxn8ecs) from working:

```cpp
namespace M {
    // some unrelated type, possibly declared far away from us
    struct Mask { /* ... */ };
    auto operator|(Mask, Mask) -> Mask;

    auto something(N::Permission permissions) -> void {
        using enum N::Permission;
        if ((permissions | Write) == Write) { // error
            // do some writing
        }
    }
}
```

That fails too — lookup for `permissions | Write` will find the `operator|(Mask, Mask)` function. It doesn't matter that it's wholly unrelated to our type and not even a _viable_ candidate, lookup stops there, we never get to the global namespace.

## Fixing this in C++26

We can get this working in C++26 in one of two ways.

The most direct way is to explicitly bring all the global namespace operators into our own namespace — which allows ADL to find them:

```cpp
namespace N {
    enum class [[=std::bitmask_type]] Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };

    using ::operator|, ::operator&;
}
```
{: data-line="9"}

This has to be specifically `using`, not `using namespace`, and you have to enumerate every operator. It's tedious, but [it works](https://godbolt.org/z/Taxqx7GW9). Of course, for the real library, you'd also have to bring in `^`, `|=`, `&=`, `^=`, and `~`. There's no short-hand for that, you gotta just write out 7 names.

Another way is to simply abandon the pull-based annotation approach and write a C macro:

```cpp
namespace N {
    enum class Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };

    MY_LIB_MAKE_BITMASK_OPERATOR(Permission)
}
```
{: data-line="9"}

That's a pretty straightforward macro to write, since we don't need to know anything about `Permission` other than how to spell its name. This way, our operators are born in our own namespace, so everything just works immediately. And for this case, a C macro is... fine? Alternatively, you could have a C macro that brings in all the global operators and keep the annotation, that works too.

## A Complete Solution: Code Injection

Using the kind of code injection that we're proposing in [P4380](https://wg21.link/p4380), we can provide a complete *push*-based solution to this problem, similar to the C macro approach, except more structured. I can do it in two different ways, whichever you prefer is just a matter of taste I think:

* an annotation on the enum that injects operators
* a declaration macro to inject the operators

In both cases, the operators end up in the same namespace as the enum, so ADL just works as expected.

### Annotation-based

We can implement an annotation that on enum completion will inject all the operator functions that we need:

```cpp
struct BitmaskType {
    static consteval auto on_complete(std::meta::info ty) -> void {
        queue_injection(^^{
            constexpr auto operator+(\(ty) e) {
                return std::to_underlying(e);
            }

            constexpr auto operator~(\(ty) e) -> \(ty) {
                return \(ty)(~+e);
            }
        });

        using enum std::meta::operators;
        auto binary = [=](std::meta::operators op, std::meta::operators op_eq){
            queue_injection(^^{
                constexpr auto operator \(op)(\(ty) lhs, \(ty) rhs) -> \(ty) {
                    return \(ty)(+lhs \(op) +rhs);
                }

                constexpr auto operator \(op_eq)(\(ty)& lhs, \(ty) rhs) -> \(ty)& {
                    lhs = lhs \(op) rhs;
                    return lhs;
                }
            });
        };

        binary(op_pipe, op_pipe_equals);
        binary(op_ampersand, op_ampersand_equals);
        binary(op_caret, op_caret_equals);
    }
};

inline constexpr auto bitmask_type = BitmaskType();
```

This also adds a unary `operator+` to convert the enum to its underlying type, which I've found to be a useful and terse pattern for that operation. But otherwise, this goes through and injects all the operators that we need, so that now adding `[[=std::bitmask_type]]` to our enum [actually works](https://compiler-explorer.com/z/Tc7qnsYcj) without needing additional `using` declarations:

```cpp
namespace N {
    enum class [[=std::bitmask_type]] Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };

    // no additional code here
}
```

### Macro-based

The macro approach has a [very similar](https://compiler-explorer.com/z/P48h961es) implementation to the annotation approach, it's just that the usage is a separate call rather than annotation:

```cpp
template <class E> requires std::is_enum_v<E>
__macro bitmask_type() {
    auto ret = ^^{
        constexpr auto operator+(\(^^E) e) {
            return std::to_underlying(e);
        }

        constexpr auto operator~(\(^^E) e) -> \(^^E) {
            return \(^^E)(~+e);
        }
    };

    using enum std::meta::operators;
    auto binary = [&](std::meta::operators op, std::meta::operators op_eq){
        return ^^{
            constexpr auto operator \(op)(\(^^E) lhs, \(^^E) rhs) -> \(^^E) {
                return \(^^E)(+lhs \(op) +rhs);
            }

            constexpr auto operator \(op_eq)(\(^^E)& lhs, \(^^E) rhs) -> \(^^E)& {
                lhs = lhs \(op) rhs;
                return lhs;
            }
        };
    };

    ret += binary(op_pipe, op_pipe_equals);
    ret += binary(op_ampersand, op_ampersand_equals);
    ret += binary(op_caret, op_caret_equals);
    return ret;
}
```

Used like:

```cpp
namespace N {
    enum class Permission {
        None    = 0,
        Read    = 1 << 0,
        Write   = 1 << 1,
        Execute = 1 << 2,
    };

    std::bitmask_type!<Permission>();
}
```

## Bonus Example: Defaulting Equality

One particular form of generating operator functions was a C++20 language feature that I was heavily involved with: the new comparison operator rules, which allow for defaulting the comparison operators. That's a _language_ feature, but with the ability to do code generation, we can implement it purely in library. I had this example in P4380 as well, but here is a more expanded version that also properly handles arrays:

```cpp
template <class T>
concept EqComparable = requires (T const& t) {
  static_cast<bool>(t == t);
};

template <class T>
constexpr auto array_eq(T const& lhs, T const& rhs) -> bool {
    if constexpr (std::is_array_v<T>) {
        return std::ranges::equal(lhs, rhs, [](auto const& x, auto const& y){
            return array_eq(x, y);
        });
    } else {
        return lhs == rhs;
    }
}

struct Eq_t {
    consteval auto inject_members(std::meta::info r) const
        -> std::meta::token_sequence
    {
        auto subobjects = subobjects_of(r, std::meta::access_context::unchecked());
        if (not std::ranges::all_of(subobjects, [](std::meta::info o){
            return extract<bool>(substitute(^^EqComparable,
                                            {remove_all_extents(type_of(o))}));
            }))
        {
            // not all comparable? defined as deleted
            return ^^{
                friend constexpr bool operator==(\(r) const&, \(r) const&) = delete;
                friend constexpr bool operator!=(\(r) const&, \(r) const&) = delete;
            };
        }

        std::meta::list_builder cmp(^^{ && });
        for (std::meta::info s : subobjects) {
            if (is_array_type(type_of(s))) {
                cmp += ^^{ ::array_eq(__lhs.\(s), __rhs.\(s)) };
            } else {
                cmp += ^^{ (__lhs.\(s) == __rhs.\(s)) };
            }
        }

        if (subobjects.empty()) {
            cmp += ^^{ true };
        }

        return ^^{
            friend constexpr bool operator==(\(r) const& __lhs [[maybe_unused]],
                                             \(r) const& __rhs [[maybe_unused]]) {
                return \(cmp);
            }

            friend constexpr bool operator!=(\(r) const& __lhs, \(r) const& __rhs) {
                return not (__lhs == __rhs);
            }
        };
    }
};

inline constexpr Eq_t Eq{};
```

And with that, we get [the desired behavior](https://compiler-explorer.com/z/nG9fbrEfb):

```cpp
struct [[=Eq]] P {
  int x;
  int y;
  int z[2][2];
};
static_assert(P{1, 2, {}} == P{1, 2, {}});
static_assert(P{1, 2, {}} != P{1, 3, {}});
static_assert(P{1, 2, {1, 2, 3, 4}} != P{1, 2, {1, 2, 3, 5}});
```

And since here we're injecting `operator==` and `operator!=` as member functions, we don't have this issue with being able to find our operators. They're always there.

> As a *bonus* bonus, my implementation of `array_eq` has to recursively call itself — I can't just pass `array_eq` to `std::ranges::equal` because that's a function template. We have to lift it into a lambda, which I did by hand:
> ```cpp
> std::ranges::equal(lhs, rhs, [](auto const& x, auto const& y){
>     return array_eq(x, y);
> })
> ```
> But once we start using macros, might as well keep solving problems with macros. We can introduce a `lift` macro:
> ```cpp
> std::ranges::equal(lhs, rhs, lift!(array_eq))
> ```
> which just does the lambda wrapping internally, and that's a [pretty simple macro](https://compiler-explorer.com/z/rWMbeYj5r) since you could write it as a C macro as well.
{:.prompt-info}

## The Road to Push-based Customization

Our pull-based customization capabilities have increased dramatically with the addition of reflection and annotations. But, pull-based customization is inherently limited and we still cannot do push-based customization in C++ yet.

> Unless you count using C macros. That works fine for this problem, but it wouldn't for either of the formatting or structured bindings examples from the previous post. And also... C macros.
{:.prompt-info}

I'm hopeful that token sequence injection can bridge that gap. That they give us a way to, ergonomically, emit customizations where they need to go, so that people like me don't have to write posts about the caveats and limitations of customization facilities that look like they work — because sometimes they just don't.

We're still early stages yet with this design, but I personally think it's quite promising.