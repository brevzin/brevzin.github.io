---
layout: post
title: "Type-based vs Value-based Reflection"
category: c++
tags:
 - c++
 - c++26
 - reflection
---

Frequently, whenever the topic of Reflection comes up, I see a lot of complains specifically about the new syntax being added to support Reflection in C++26. I've always thought of that as being largely driven by unfamiliarity — this syntax is new, unfamiliar, and thus bad. I thought I'd take a different tactic in this post: let's take a problem that can only be solved with Reflection and compare what the solution would look like between:

* the C++26 value-based model
* the Reflection Technical Specification (TS)'s type-based model

Don't worry if you're not familiar with the Reflection TS, I'll go over it in some detail shortly.

But first, today's problem. C++20 introduced the concept of _structural type_. These are the kinds of types that you can use as ~~non-type~~ constant template parameters. The definition of [structural type](https://eel.is/c++draft/temp.param#def:type,structural) is:

> A *structural type* is one of the following:
>
> * a scalar type, or
> * an lvalue reference type, or
> * a literal class type with the following properties:
>     * all base classes and non-static data members are public and non-mutable and
>     * the types of all base classes and non-static data members are structural types or (possibly multidimensional) arrays thereof.

There is no trait for this in the standard library today. How would we write one? Without reflection, this isn't implementable. The first two bullets are easy, but even the most clever Boost.PFR tricks don't do anything to help with the third. Let's see how it's done.

## The Reflection TS

The Reflection TS (whose draft you can find [here](https://cplusplus.github.io/reflection-ts/draft.pdf)) was published in March, 2020. It came the work done by Matúš Chochlík, Axel Naumann, and David Sankel in [P0194](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0194r6.html).

The design was a _type-based_ model. It introduced a new operator, `reflexpr(E)`, which which gave you a _unique_ type. What I mean by unique is that `reflexpr(A)` and `reflexpr(B)` are the same type if and only if `A` and `B` are the same entity.

That is the only new part of the language, which only yields types. The library side includes a bunch of template metafunctions to use for queries. For instance, the first example in the paper is, of course, enum-to-string:

```cpp
enum E { first, second };
using E_m = reflexpr(E);
using namespace std::experimental::reflect;
using first_m = get_element_t<0, get_enumerators_t<E_m>>;
std::cout << get_name_v<first_m> << std::endl; // prints "first"
```

This example also demonstrates the other important concept to point out in the Reflection TS: what is `get_enumerators_t<E_m>`? In TS terms, that is called an _object sequence_ (whereas `E_m` is just an _object_). An object sequence is basically a typelist of objects — except that they're not strictly specified as such (and in the one implementation of the TS that I'm aware of, they're not implemented as such either). Instead, the TS came with other metafunctions to manipulate them.

That's basically the design in a nutshell:

* `reflexpr(E)` gives you a unique type representing properties of `E`
* the library comes with a lot of queries on reflection types
* some of those queries return values (like `get_name_v`), some return types — which can be reflection types (like `get_element_t`), and some return object sequences (like `get_enumerators_t`).

On the whole, the above should be fairly familiar. It's regular template metaprogramming. It's simple.

## Implementing the Reflection TS

It occurred to me recently that I could actually implement the Reflection TS on top of the [p2996 design](https://wg21.link/p2996). I'm not going to implement the whole thing, I will instead do just enough to solve the problem I posed at the beginning of this blog post. But I'll walk through how to do that, which should help shine light both on how the TS works and how the p2996 design works.

To start with, we need a reflection operator which returns a unique type per entity. We can do that with a macro:

```cpp
namespace std::reflect {
    template <meta::info R>
    struct Reflection {
        static constexpr auto value = R;
    };

    #define reflexpr(E) ::std::reflect::Reflection<^^E>
}
```

In the value-based reflection model, `^^E` gives us a unique value for each entity, with uniqueness defined exactly how we need it. So we simply need to lift that into a type.

The other fundamental piece we need is an object sequence, which I will just just implement as a type-list (even though, as mentioned, it's not specified as such):

```cpp
namespace std::reflect {
    template <class... R>
    struct Sequence { };
}
```

So far so good.

Next, the Reflection TS introduced a lot of `concept`s (it was introduced at the same time as Concepts in C++20) to help make it easier understand the API and catch invalid uses as early as possible.

The root concept is `Object`, which represents a reflection object, and everything else builds on top of that. There was also `ObjectSequence`, for object sequences. For some reason, `ObjectSequence` refined `Object`. I'm not sure why that's helpful, since these are distinct kinds — so for simplicity I'm not going to do that, but otherwise I'm going to try to keep changes to a minimum.

In my implementation here, an `Object` is just a specialization of `std::reflect::Reflection` and `ObjectSequence` is just a specialization of `std::reflect::Sequence`. So I'll add a helper concept for that:

```cpp
namespace std::reflect {
    template <meta::info R>
    struct Reflection {
        static constexpr auto value = R;
    };

    template <class... R>
    struct Sequence { };

    #define reflexpr(E) ::std::reflect::Reflection<^^E>

    template <class T, meta::info Z>
    concept Specializes = has_template_arguments(^^T)
                      and template_of(^^T) == Z;

    template <class T>
    concept Object = Specializes<T, ^^Reflection>;
    template <class T>
    concept ObjectSequence = Specializes<T, ^^Sequence>;
}
```
{: data-line="12-19" .line-numbers }

Note here that we don't have universal template parameters, but we can use reflection parameters as a close enough substitute. As an implementation detail, it works well enough.

The rest of the hierarchy of concepts that we'll need is based on properties what the `Object` in question represents. We have queries for all of those, so we can just use them:

```cpp
namespace std::reflect {
    template <class T>
    concept Base = Object<T> and is_base(T::value);
    template <class T>
    concept Named = Object<T> and has_identifier(T::value);
    template <class T>
    concept Typed = Object<T> and has_type(T::value);
    template <class T>
    concept Type = Object<T> and is_type(T::value);
    template <class T>
    concept Record = Type<T> and is_class_type(T::value);
    template <class T>
    concept Class = Record<T> and not is_union_type(T::value);
    template <class T>
    concept Enum = Type<T> and is_enum_type(T::value);
    template <class T>
    concept RecordMember = Object<T> and is_class_member(T::value);
}
```

> There are a few other concepts in this hierarchy, like `Scope` and `ScopeMember`, that I'm omitting for simplicity. Also p2996 right now does not actually expose `has_type`, it's for exposition-only, and this is the first time I've actually needed it. We should probably expose it, on the premise that we've done that for other functions (like `has_parent`), but until then it's straightforward enough to implement.
{:.prompt-info}

Okay, concepts are fun, but we haven't even done any queries yet. Let's at least get that first example going. I need:

* `get_element_t`
* `enumerators_t` (which in the TS was renamed to `get_enumerators_t`)
* `get_name_v`

### `get_element_t`

`get_element_t` is the simplest. It takes a `size_t I` and an `ObjectSequence T` and returns the `I`th element of `T`. Boost.Mp11 fans might recognize this at `mp_at_c` (with the arguments flipped). I'd implement that this way:

```cpp
namespace std::reflect {
    template <class... R>
    struct Sequence { };

    template <class T>
    concept ObjectSequence = Specializes<T, ^^Sequence>;

    template <size_t I, ObjectSequence Seq>
    using get_element_t = [: template_arguments_of(^^Seq)[I] :];
}
```
{: data-line="8-9" .line-numbers }

The `I`th element of `Seq` is the `I`th template argument of that type. An alternative approach, which might compile faster, would be to add an alias template inside of `Sequence` which takes advantage of the new pack indexing facility:

```cpp
namespace std::reflect {
    template <class... R>
    struct Sequence {
        template <size_t I>
        using nth = R...[I];
    };

    template <class T>
    concept ObjectSequence = Specializes<T, ^^Sequence>;

    template <size_t I, ObjectSequence Seq>
    using get_element_t = Seq::template nth<I>;
}
```
{: data-line="4-5,11-12" .line-numbers }

### `get_enumerators_t`

The next piece we need for the example is `get_enumerators_t`. This takes an `Enum` and yields an `ObjectSequence` of enumerators. In order to implement this, we need to use a function which is one of the most surprisingly useful functions in the value-based design: `substitute`.

`substitute` is actually quite simple. It takes a reflection of a template and a sequence of reflections of template arguments and gives back a reflection of the specialization. For instance, `substitute(^^std::vector, {^^int})` gives you back `^^std::vector<int>`. Or, `substitute(^^std::array, {^^int, std::meta::reflect_constant(4)})` gives you back `std::array<int, 4>`. The call to `std::meta::reflect_constant` is necessary because we need to provide _reflections_ to `substitute`, so we need to take our `4` and produce a reflection of the value `4`. That's what `reflect_constant` does.

> For C++26, we do not yet have reflections of _expressions_. It's possible that a future extension would simply allow `^^(4)` there. The parentheses might be necessary because unlike the reflection syntax, which isn't that bad, C++ has plenty of actually really bad syntax. Consider `^^int()` — what should that give you a reflection of? Obviously, a reflection of the _type_ "function with no parameters that returns `int`." Were you expecting something else?
{:.prompt-info}

For this particular metafunction, we need to start with a sequence of enumerators and use them to produce a specialization of `Sequence`, whose template parameters are specializations of `Reflection`. Put differently, if we had a pack `E...` of the reflections of the enumerators of `T`, then we need to give back the type `Sequence<Reflection<E>...>`.

`substitute` is how we get there:

```cpp
namespace std::reflect {
    template <Enum T>
    using get_enumerators_t = [: []{
        vector<meta::info> args;
        for (meta::info e : enumerators_of(T::value)) {
            args.push_back(substitute(^^Reflection,
                                      {meta::reflect_constant(e)}));
        }
        return substitute(^^Sequence, args);
    }() :];
}
```

We start with `enumerators_of`, to get reflections of enumerators. And then we turn each one of those into a reflection of the appropriate specialization of `Reflection`. And that entire sequence is passed as template parameters to `substitute` into `Sequence`. That gives us a _reflection_ of the `Sequence` we want, so we need to splice the result to get back to the type that we want.

It's worth walking through this again with a short example. Let's say we have

```cpp
enum E { e1, e2, e3 };
```

Our sequence of steps is:

1. We start with `^^E`.
2. `enumerators_of` gives us `std::vector{^^E::e1, ^^E::e2, ^^E::e3}`.
3. We need to turn that first into `std::vector{^^Reflection<^^E::e1>, ^^Reflection<^^E::e2>, ^^Reflection<^^E::e2>}`. That `for` loop is producing this `vector` of reflections.
4. So that we can `substitute` into `^^Sequence<Reflection<^^E::e1>, Reflection<^^E::e2>, Reflection<^^E::e2>>`.
5. Finally, we have reflection representing the type we want, so we splice it to get the type.

This pattern is going to come up a few times in the TS, so I will refactor it this way:

```cpp
namespace std::reflect {
    inline constexpr auto into_ref = [](meta::info r){
        return substitute(^^Reflection, {meta::reflect_constant(r)});
    };

    inline constexpr auto into_seq = [](auto&& r){
        return substitute(^^Sequence,
                          r | views::transform(into_reflection));
    };

    template <Enum T>
    using get_enumerators_t = [: into_seq(enumerators_of(T::value)) :];
}
```

> Note that all the sequence algorithms take any appropriate range of reflections, so the `transform` just works. You don't have to turn it into `vector<meta::info>` at the end or any specific container. Earlier revisions of the design took a `span<info const>`, but this proved cumbersome in practice.
{:.prompt-info}

### `get_name_v`

Lastly, we need a name. The interesting thing here is that `get_name<T>::value` in the TS is, specifically, a `char const(&)[N]` that refers to a null-terminated byte string. In the value-based reflection design, `identifier_of` gives you a `string_view` (that is specified to be null-terminated). However, nothing I'm going to do relies on `get_name<T>::value` specifically being a reference to an array, and `get_name_v<T>` is a pointer anyway, so I will again simplify a bit here:

```cpp
namespace std::reflect {
    template <Named T>
    constexpr auto get_name_v = identifier_of(T::value).data();
}
```

> We can still produce a `char const(&)[N]` if desired, using `substitute`. Have I mentioned that this is a very useful function? You can see an implementation of how to get there in [P3617](https://wg21.link/p3617), which was recently approved for C++26.
>
> Using the proposed `reflect_constant_string` (which returns a reflection of an array), that would look like this:
> ```cpp
> namespace std::reflect {
>   template <Named T>
>   struct get_name {
>     static constexpr auto& value =
>       [: meta::reflect_constant_string(identifier_of(T::value)) :];
>   };
> }
> ```
{:.prompt-info}

And with that, we can test out our implementation to see if it works ([it does](https://compiler-explorer.com/z/Ys37ToTb5)).

### A First Comparison

We haven't yet implemented all the pieces we need to implement `is_structural` using the Reflection TS, but we have this first example. Let's compare what it would look like to write a function that takes an `enum` and returns the string name of its first enumerator. It may not be the most compelling reflection use-case, but it still requires interesting things.

```cpp
template <class T>
consteval auto first_enum_ts() -> std::string_view {
    using namespace std::reflect;
    return get_name_v<get_element_t<0, get_enumerators_t<reflexpr(T)>>>;
}

template <class T>
consteval auto first_enum_value() -> std::string_view {
    return identifier_of(enumerators_of(^^T)[0]);
}
```

The first thing to notice is that there is a direct one-to-one correspondence for all of the operations. This shouldn't be too surprising, since the type-based design heavily informed the value-based design:

|type-based|value-based|
|-|-|
|`reflexpr(T)`|`^^T`|
|`std::reflect::get_enumerators_t<R>`|`enumerators_of(r)`|
|`std::reflect::get_element_t<0, Seq>`|`seq[0]`|
|`std::reflect::get_name_v<R>`|`identifier_of(r)`|

Now, with the type-based model, all the names have to either be qualified or brought in via `using namespace`. That's not new, I frequently have a `using namespace boost::mp11;` when using Boost.Mp11. But in the value-based model, it's unnecessary because we rely on argument-dependent lookup.

The other thing to notice is that we had to use a metafunction to pull out the first element in the type-based model, but in the value-based one we didn't have to use a dedicated reflection function — we were able to just used the index operator. That's pretty nice.

### `get_bases_classes_t` and `get_data_members_t`

Getting back to the problem I wanted to implement, there are a few more pieces we need. The definition of structural relies on recursing through base classes and non-static data members, so we will need the ability to do so. Now that we've provided a nice utility for converting a reflection range into a object sequence, we can simply reuse that:

```cpp
namespace std::reflect {
    inline constexpr auto into_reflection = [](meta::info r){
        return substitute(^^Reflection, {meta::reflect_constant(r)});
    };

    inline constexpr auto into_seq = [](auto&& r){
        return substitute(^^Sequence,
                          r | views::transform(into_reflection));
    };

    template <Enum T>
    using get_enumerators_t = [: into_seq(enumerators_of(T::value)) :];

    static constexpr auto unchecked =
        std::meta::access_context::unchecked();

    template <Class T>
    using get_base_classes_t = [: into_seq(
        bases_of(T::value, unchecked)
    ) :];

    template <Class T>
    using get_nonstatic_data_members_t = [: into_seq(
        nonstatic_data_members_of(T::value, unchecked)
    ) :];
}
```
{: data-line="14-25" .line-numbers }

Easy enough.

> There's one thing I changed in the API here. In the Reflection TS, the metafunction is `get_data_members`. It returned _all_ the data members — static and non-static. So if you wanted just the non-static data members (as you usually do), you would need to do a filter — something like `boost::mp11::mp_remove_if<std::reflect::get_data_members_t<T>, std::reflect::is_static>`. That's pretty tedious for a common operation, and I suspect that were the TS to be standardized, somebody would have pointed this out.
>
> On the other hand, the p2996 design does not have a simple function to get all the data members. You would have to either get all the members (`members_of`) and filter down or merge the non-static (`nonstatic_data_members_of`) and static (`static_data_members_of`) data members. So in this case, copying the TS design would've meant more work to implement something less useful.
{:.prompt-info}

At this point let's stop and do another quick comparison — another fairly silly little metafunction. Before, we looked at the name of the first enumerator, now let's look at the _type_ of the first non-static data member.

```cpp
template <class T>
using first_nsdm_type_ts =
        std::reflect::get_type_t<
            std::reflect::get_element_t<0,
                std::reflect::get_nonstatic_data_members_t<
                    reflexpr(T)>>>;

template <class T>
using first_nsdm_type_value = [:
    type_of(nonstatic_data_members_of(
        ^^T, std::meta::access_context::unchecked()
        )[0])
    :];
```

As with the earlier example, we have a direct 1-1 mapping of operations... almost:

|type-based|value-based|
|-|-|
|`reflexpr(T)`|`^^T`|
|`std::reflect::get_nonstatic_data_members_t<R>`|`nonstatic_data_members_of(r, std::meta::access_context::unchecked())`|
|`std::reflect::get_element_t<0, Seq>`|`seq[0]`|
|`std::reflect::get_type_t<R>`|`type_of(r)`|
|---|`[: r :]`|

The p2996 design for getting bases and non-static data members is, unfortunately, extremely verbose. But the type-based design has its own issue with verbosity due to having to qualify all the metafunctions. If we put the type-based solution in a context where we can `using namespace std::reflect`, that solution becomes a lot more palatable. And likewise if we add a wrapper for `nsdms()` or `fields_of()` that returns all the non-static data members:

```cpp
template <class T>
using first_nsdm_type_ts =
    get_type_t<get_element_t<0, get_nonstatic_data_members_t<reflexpr(T)>>>;

template <class T>
using first_nsdm_type_value = [: type_of(fields_of(^^T)[0]) :];
```

Now, this solution wasn't quite what I expected. When I'd started implementing this example using the TS, I thought I would need _one more_ metafunction on the type-based solution. To fill in that empty box in the bottom left corner:

|type-based|value-based|
|-|-|
|`reflexpr(T)`|`^^T`|
|`get_nonstatic_data_members_t<R>`|`fields_of(r)`|
|`get_element_t<0, Seq>`|`seq[0]`|
|`get_type_t<R>`|`type_of(r)`|
|`get_reflected_type_t<R>` ??|`[: r :]`|

The function `std::meta::type_of(r)` takes a reflection of a typed entity and produces a _reflection_ of a type. But the metafunction `std::reflect::get_type_t<R>` takes a reflection of a typed entity and produces _the type_ directly. What I mean is:

```cpp
// let's take some variable
constexpr int v = 42;

// in the value-based design, this is a *reflection* of int
static_assert(type_of(^^v) == ^^int);

// the TS, this is already int
using T = std::reflect::get_type_t<reflexpr(v)>;
static_assert(std::same_as<T, int>); // int, not reflexpr(int)
```


On the one hand, that saves a step, if that's what you really want. On the other hand, it requires re-invoking `reflexpr` if you need to then do more reflection things with it. For instance, if I wanted the first non-static data member's type _of the first non-static data member_, in the value-based model I just call `fields_of` again but in the TS model I'd have to call `reflexpr` first.

In any case, I think one of the unheralded benefits of the new syntax — at least one that I hadn't thought about before going through this exercise — is that we have distinct syntax for going _into_ (`^^T`) and _out of_ (`[: r :]`) the reflection domain. In the Reflection TS, there was only distinct syntax for going into the domain (`reflexpr` was a keyword, so would have shown up clearly). But on the way out were just regular metafunctions — `get_type_t`, `get_pointer_v`, etc. I think there's something to be said for having this stand out.

### A few predicates more

Alright lastly we just need a few predicates. We need to be able to check if a base or data member is public and mutable. The TS didn't have a way to check for `mutable`, but p2996 does, so we'll just add the equivalent:

```cpp
namespace std::reflect {
    template <class T> requires RecordMember<T> or Base<T>
    inline constexpr bool is_public_v = is_public(T::value);

    template <RecordMember T>
    inline constexpr bool is_mutable_member_v = is_mutable_member(T::value);
}
```

## A type-based implementation

We have all the pieces, now let's solve the problem.

There are basically two issues that we have to deal with in writing an `is_structural` type trait:

1. How to properly handle recursion, and
2. How to properly guard instantiations.

What I mean by the second one is that we can't just write a linear branch like this:

```cpp
template <class T>
inline constexpr bool is_structural =
    std::is_scalar_v<T>
    or std::is_lvalue_reference_v<T>
    or std::is_class_v<T> and
        boost::mp11::mp_all_of<
            std::reflect::unpack_sequence_t<
                boost::mp11::mp_list,
                std::reflect::get_base_classes_t<reflexpr(T)>
            >,
            std::reflect::is_public
        >::value
    ;
```

This is only part of the implementation, I'm just checking that class types have all-public base classes to start. And checking this on class types _does work_:

```cpp
struct B { };
struct D : B { };
static_assert(is_structural<B>); // yes
static_assert(is_structural<D>); // yes
```

It's just that checking it on non-class types doesn't:

```cpp
static_assert(is_structural<int>); // error
```

That's because boolean expressions like this short-circuit evaluation, but they don't short-circuit _instantiation_. This is still trying to instantiate `get_base_classes_t` with `reflexpr(int)`, which is invalid because that metafunction is constrained on `Class` (which `int` is not).

So we need a different strategy.

There's basically two approaches I know of to handle this. The first is specialization. We have three cases that happen to be completely disjoint (scalar, lvalue reference, and class type), so we can just handle them separately:

```cpp
template <class T>
inline constexpr bool is_structural = false;

template <class T> requires std::is_scalar_v<T>
inline constexpr bool is_structural<T> = true;

template <class T> requires std::is_lvalue_reference_v<T>
inline constexpr bool is_structural<T> = true;

template <class T> requires std::is_class_v<T>
inline constexpr bool is_structural<T> =
    boost::mp11::mp_all_of<
            std::reflect::unpack_sequence_t<
                boost::mp11::mp_list,
                std::reflect::get_base_classes_t<reflexpr(T)>
            >,
            std::reflect::is_public
        >::value;
```

That approach works great. But I'm not a huge fan of it for this particular problem. Template specialization is a _best match_ algorithm. Our problem, though, calls for a linear sequence of bullets. It works, but it's not a direct match for the algorithm we want to express, which can make things harder to reason about. In particular, if our cases _weren't_ disjoint, we'd have to spend more time working out how to actually express them.

I tend to prefer linearity. Which, in this case, means `if constexpr`:

```cpp
template <class T>
inline constexpr bool is_structural = []{
    if constexpr (std::is_scalar_v<T>) {
        return true;
    } else if constexpr (std::is_lvalue_reference_v<T>) {
        return true;
    } else if constexpr (std::is_class_v<T>) {
        return boost::mp11::mp_all_of<
                std::reflect::unpack_sequence_t<
                    boost::mp11::mp_list,
                    std::reflect::get_base_classes_t<reflexpr(T)>
                >,
                std::reflect::is_public
            >::value;
    } else {
        return false;
    }
}();
```

That works too. And sure, both this approach and the previous one can be simplified a bit by combining cases, I'm not trying to code golf here. The nice part of wrapping this in a lambda (or making `is_structural` a `consteval` function) is that we have a nice place to stick a `using namespace` in there, which makes the implementation much more readable:

```cpp
template <class T>
consteval auto is_structural() -> bool {
    if constexpr (std::is_scalar_v<T>) {
        return true;
    } else if constexpr (std::is_lvalue_reference_v<T>) {
        return true;
    } else if constexpr (std::is_class_v<T>) {
        using namespace boost::mp11;
        using namespace std::reflect;
        return mp_all_of<
            unpack_sequence_t<mp_list, get_base_classes_t<reflexpr(T)>>,
            is_public
        >::value;
    } else {
        return false;
    }
}
```

Now, for the recursion part. We need to not just check that all of the base classes are _public_, but also that they're _structural_. We could add a helper

```cpp
template <auto F>
struct Func {
    template <class... Ts>
    using fn = decltype(F.template operator()<Ts...>());
};
```

Which could drive our recursion:

```cpp
template <class T>
inline constexpr bool is_structural = []{
    if constexpr (std::is_scalar_v<T>) {
        return true;
    } else if constexpr (std::is_lvalue_reference_v<T>) {
        return true;
    } else if constexpr (std::is_class_v<T>) {
        using namespace std::reflect;
        using namespace boost::mp11;
        return mp_all_of_q<
                unpack_sequence_t<mp_list, get_base_classes_t<reflexpr(T)>>,
                Func<[]<Base B>{
                        return mp_bool<
                            is_public_v<B>
                            and is_structural<get_type_t<B>>
                        >();
                    }>
            >::value
            and
            mp_all_of_q<
                unpack_sequence_t<mp_list,
                    get_nonstatic_data_members_t<reflexpr(T)>>,
                Func<[]<RecordMember M>{
                        return mp_bool<
                            is_public_v<M>
                            and not is_mutable_member_v<M>
                            and is_structural<std::remove_all_extents_t<
                                get_type_t<M>>>
                        >();
                    }>
            >::value;
    } else {
        return false;
    }
}();
```

That's a complete solution. Could even do a little bit better by having a dedicated predicate lambda (so that it can just return `bool`) and handling the base classes and non-static data members at the same time:

```cpp
template <auto F>
struct Pred {
    template <class... Ts>
    using fn = mp_bool<F.template operator()<Ts...>()>;
};

template <class T>
inline constexpr bool is_structural = []{
    if constexpr (std::is_scalar_v<T>) {
        return true;
    } else if constexpr (std::is_lvalue_reference_v<T>) {
        return true;
    } else if constexpr (std::is_class_v<T>) {
        using namespace std::reflect;
        using namespace boost::mp11;

        using Bases = unpack_sequence_t<
            mp_list, get_base_classes_t<reflexpr(T)>>;
        using Members = unpack_sequence_t<
            mp_list, get_nonstatic_data_members_t<reflexpr(T)>>;
        return mp_all_of_q<
                mp_append<Bases, Members>,
                Pred<[]<Object O>{
                    if constexpr (RecordMember<O>) {
                        if (is_mutable_member_v<O>) {
                            return false;
                        }
                    }

                    return is_public_v<O>
                        and is_structural<
                            std::remove_all_extents_t<get_type_t<O>>>;
                }>
            >::value;
    } else {
        return false;
    }
}();
```

We have to guard the instantiations of `is_mutable_member_v` with an `if constexpr` for the same reason that we had to guard the instantiations of `get_base_classes_t` and `get_nonstatic_data_members_t`.

On the whole, this follows the definition of structural reasonably well? We use Boost.Mp11 to do the sequence stuff, and the `Pred` trick here allows for recursion without too much trouble. This is, at least, the best way I could come up with of solving the problem. I'm open to better ideas!

## A value-based implementation

Now that we saw how to do this with the type-based approach, let's see how this looks with the value-based approach. To start with, I'm doing to have a very different signature. Instead of a boolean variable template as I just showed above (or a similar `consteval` function template), I am going to write a _function_. Not a function template, just a function:

```cpp
consteval auto is_structural(std::meta::info type) -> bool;
```

It turns out that, while we have new syntax for getting into (`^^e`) and out of (`[: e :]`) the value domain, once you're in the value domain — it's nice to just stay there. And so I expect the most common approach will just be... functions. Functions are, after all, simpler. And, for problems like this, it cannot be specialized — which isn't a huge benefit, since I don't think people specializing things they shouldn't be is necessarily a big problem, but it's nice. The syntax on the call side is slightly different — `is_structural<T>` vs `is_structural(^^T)` — but that's not really a big deal right now. And you could always just add a variable template that itself defers to the function.

That premise — the desire to stay in the value domain — is why we're also adding consteval function versions of all the type traits (as you'll see shortly, and may have noticed me already using). Most of those new functions have the same name as the existing type trait, except that predicates whose name was `is_meow` become `is_meow_type`. Quick table:

|Existing Type Trait|New Function
|-|-|
|`is_scalar_v<T>`|`is_scalar_type(t)`|
|`is_convertible_v<T, U>`|`is_convertible_type(t, u)`|
|`remove_cvref_t<T>`|`remove_cvref(t)`|
|`invoke_result_t<F, T, U>`|`invoke_result(f, {t, u})`|

With that in mind, let's implement that function. As a direct translation of the rules and using the appropriate type trait functions:

```cpp
consteval auto is_structural(std::meta::info type) -> bool {
    auto ctx = std::meta::access_context::unchecked();

    return is_scalar_type(type)
        or is_lvalue_reference_type(type)
        or is_class_type(type)
            and std::ranges::all_of(bases_of(type, ctx),
                    [](std::meta::info b){
                        return is_public(b)
                           and is_structural(type_of(b));
                    })
            and std::ranges::all_of(nonstatic_data_members_of(type, ctx),
                    [](std::meta::info m){
                        return is_public(m)
                           and not is_mutable_member(m)
                           and is_structural(
                                remove_all_extents(type_of(m)));
                    });
}
```

That's it.

With the TS implementation, we had to carefully guard against the _instantiation_ of certain metafunctions based on some criteria. So we had several `if constexpr`s. With the value-based implementation, we still have to guard — but we only have to guard against the _evaluation_ of certain functions. And that can be achieved simply with the short-circuiting behavior that the logical operators provide. A simple `if` or an `and` is fine.

This can even be reduced in the same way as I showed earlier by combining the bases and non-static data members, using the `subobjects_of` API:

```cpp
consteval auto is_structural(std::meta::info type) -> bool {
    auto ctx = std::meta::access_context::unchecked();

    return is_scalar_type(type)
        or is_lvalue_reference_type(type)
        or is_class_type(type)
            and std::ranges::all_of(subobjects_of(type, ctx),
                    [](std::meta::info o){
                        return is_public(o)
                           and not is_mutable_member(o)
                           and is_structural(
                                remove_all_extents(type_of(o)));
                    });
}
```

One of the design differences that we took is that many of the predicates simply return `false` instead of being ill-formed when asking a seemingly nonsensical question. A reflection of a base class is never going to be a mutable member, but `is_mutable_member(o)` will just be `false` there. Which is what we want anyway, so we don't even have to guard that invocation.

We're doing reflection stuff here, but this really looks like regular code. We just happen to be operating on reflection objects.

## Comparing type-based to value-based

Let's compare again the two implementations of `is_structural` (which you can find [here](https://compiler-explorer.com/z/benPWqe19), including the not-quite-100 line implementation of the TS and the other examples I mentioned earlier):

```cpp
template <class T>
inline constexpr bool is_structural = []{
    if constexpr (std::is_scalar_v<T>) {
        return true;
    } else if constexpr (std::is_lvalue_reference_v<T>) {
        return true;
    } else if constexpr (std::is_class_v<T>) {
        using namespace std::reflect;
        using namespace boost::mp11;

        using Bases = unpack_sequence_t<
            mp_list, get_base_classes_t<reflexpr(T)>>;
        using Members = unpack_sequence_t<
            mp_list, get_nonstatic_data_members_t<reflexpr(T)>>;
        return mp_all_of_q<
                mp_append<Bases, Members>,
                Pred<[]<Object O>{
                    if constexpr (RecordMember<O>) {
                        if (is_mutable_member_v<O>) {
                            return false;
                        }
                    }

                    return is_public_v<O>
                        and is_structural<
                            std::remove_all_extents_t<get_type_t<O>>>;
                }>
            >::value;
    } else {
        return false;
    }
}();
```
{: .line-numbers }

vs

```cpp
consteval auto is_structural(std::meta::info type) -> bool {
    auto ctx = std::meta::access_context::unchecked();

    return is_scalar_type(type)
        or is_lvalue_reference_type(type)
        or is_class_type(type)
            and std::ranges::all_of(subobjects_of(type, ctx),
                    [](std::meta::info o){
                        return is_public(o)
                           and not is_mutable_member(o)
                           and is_structural(
                                remove_all_extents(type_of(o)));
                    });
}
```
{: .line-numbers }

C++26 reflection does bring with it new syntax and a bunch of new semantics. But the benefit is that a lot of metaprogramming starts to look more like regular programming. There is a lot _less_ syntax in the implementation side of things. For instance, there are no `<`s or `>`s in the value-based implementation at all. The solution isn't just half as long, it's also significantly less complicated, and doesn't require an extra library specifically tailored to solve the problem.

Even when we do have to use more syntax, I think it's an improvement. Consider any reflection problem that requires iterating over the members of a type. Eventually, you'll have some reflection representing a non-static data member and you have to combine that with the object in order to read the member. What does that look like?

|Type-Based|Value-Based|
|-|-|
|`obj.*std::reflect::get_pointer_v<R>`|`obj.[: r :]`|

In the type-based model, we have a metafunction (because everything is a metafunction) that gives you a pointer-to-member. Even separate from syntax preferences, this already had the problem that it wouldn't work for bit-fields and reference members. In the value-based model, we require novel syntax — but it's significantly terser, works for all non-static data member kinds, and also makes the fact that we're coming out of the reflection domain much clearer. I think that's a win.

Another distinction to point out is that template metaprogramming cannot do any mutation — all solutions have to be functional. That's why Boost.Hana looks like the way it does. That's why Boost.Mp11 is such a superior library for metaprogramming than Boost.MPL — its approach fits the problem space better. But with value-based reflection, you can write imperative code too. I used `std::ranges::all_of()` in my solution since it's exactly the algorithm for the job — but it's not the _only_ solution. You could write this in a series of regular `if` statements and regular `for` loops too if that's what you prefer:

```cpp
consteval auto is_structural(std::meta::info type) -> bool {
    if (is_scalar_type(type)) {
        return true;
    } else if (is_lvalue_reference_type(type)) {
        return true;
    } else if (is_class_type(type)) {
        auto ctx = std::meta::access_context::unchecked();
        for (std::meta::info o : subobjects_of(type, ctx)) {
            if (not is_public(o)) {
                return false;
            }
            if (is_mutable_member(o)) {
                return false;
            }
            if (not is_structural(remove_all_extents(type_of(o)))) {
                return false;
            }
        }
        return true;
    } else {
        return false;
    }
}
```
{: .line-numbers }

Not my personal preference, but just as viable.

In short, C++26's value-based reflection design does bring with it new syntax — new syntax that needs to be recognized and understood. But the benefit of the new syntax bringing us into and out of the reflection domain is that all the work that we do within the reflection domain isn't template metaprogramming anymore. It's just... programming.