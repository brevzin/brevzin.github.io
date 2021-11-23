---
layout: post
title: "Conditional Members"
category: c++
tags:
 - c++
 - c++20
 - reflection
 - metaprogramming
---

I'd previously written a post about `if constexpr` (and how it's [not broken]({% post_url 2019-01-15-if-constexpr-isnt-broken %})). I argued in that post how, broadly speaking, C++20 gives you the tools to solve the problems you want, even if they work a bit differently to D's `static if` (with one notable exception, which this post greatly expands on). Now, over the past couple years, I've been working on a project that really is a deep dive into what Andrei calls "Design by Introspection." This approach (for lack of a better definition), relies on conditioning functionality based on template parameters.

For the purposes of this post, I'm going to deal with one particular kind of design by introspection: having conditional members. There are three kinds of members that we want to be able to have conditionally (or differently) present based on template parameters:

* conditional member *functions*
* conditional member *variables*
* conditional member *types*

These are arranged roughly in how easy it is to do them in C++20, and I'll go through the issues that come up with each of these in turn. In D, you basically have one language feature to solve all of these problems and that one language feature is `if` (sometimes `static if`). In C++, we use different tools in each case.

## Conditional Member Functions

The goal here is to create a member function that only exists when the template parameters meet some criteria.

In C++20, Concepts are basically the way that we solve this problem. In C++17 and earlier, we could always add "constraints" to member function templates of class templates (i.e. using `std::enable_if`), but we couldn't add them to member functions that were not templates. The most important of these are the special member functions. You can't make a class conditionally copyable with `std::enable_if`. But in C++20, you _can_ add proper constraints (no scare quotes necessary) in all of these cases. And that just works:

```cpp
template <typename T>
class Optional {
public:
    Optional(Optional const&) requires copy_constructible<T>;
};
```

or:

```cpp
template <input_range R>
class adapted_range {
public:
    constexpr auto size() requires sized_range<R>;
};
```

In these examples, `Optional<int>` would be copy constructible, but `Optional<unique_ptr<int>>` wouldn't be. `adapted_range<vector<int>>` would have a `size()` member function but `adapted_range<filter_view<V, F>>` would not.

Using C++20 concepts to conditionally control member functions just works great.

_Nearly_ all the time. There's one kind of exception. Consider this case of writing a smart pointer. Being a pointer, I want to provide an `operator*`. But, because I also support `void`, and you can't dereference a `void*`, I need to make sure that this member function does not exist in that case. Naturally, I'll use concepts:

```cpp
template <typename T>
struct Ptr {
    auto operator*() const -> T&
        requires (!std::is_void_v<T>);
};

Ptr<void> p; // error
```

That is [already ill-formed](https://godbolt.org/z/4TbMsfxhc). I'm not even trying to `*p` anywhere, simply creating the type. What happened to my constraint?

The issue here is that Concepts don't actually do conditional member functions. It's not that `Optional<unique_ptr<int>>` _had no_ copy constructor or that `adapted_range<filter_view<V, F>>` _had no_ member function named `size()`. They do have those functions. It's just that, when it comes to overload resolution, those (actually-existing) functions are removed from consideration at that point.

Typically, there's no distinction between these cases. There's not really much of a difference between `adapted_range` not having a `size()` member function and it having one that you simply cannot invoke. You can't really differentiate.

But in this case there is.

The rule is that when a class template is instantiated (as in the declaration of `Ptr<void> p` above), all of the signatures of its member functions are instantiated (this is [\[temp.inst\]/3](http://eel.is/c++draft/temp.inst#3)). And doing so requires forming `T&`, which is not a valid thing to do when `T` is `void`, and this blow ups at that point (gcc and clang's errors clearly point to this, MSVC's not so much).

The way to do this correctly in C++20 is to either wrap the `T&` in something that correctly handles `void` (`std::add_lvalue_reference_t<void>` is `void`):

```cpp
template <typename T>
struct Ptr {
    auto operator*() const -> std::add_lvalue_reference_t<T>
        requires (!std::is_void_v<T>);
};

Ptr<void> p; // ok
```

Or to turn the whole function into a function template to delay its instantiation (now we're returning `U&`, not `T&`):

```cpp
template <typename T>
struct Ptr {
    template <typename U=T> requires (!std::is_void_v<U>)
    auto operator*() const -> U&;
};

Ptr<void> p; // also ok
```

Personally though, I dislike both of these solutions. The goal here is to have `operator*` exist only when `T` isn't `void`. Concepts unfortunately don't help here.

But Concepts do help most of the rest of the time. While they don't literally give us conditional member functions, they do basically help solve that problem.

## Conditional Member Variables

If you browse through the spec for Ranges ([\[ranges\]](http://eel.is/c++draft/ranges)), there are several cases where we want to have a member variable that is present only under certain conditions. Ranges isn't that unique in this sense, there are plenty of situations where this sort of thing comes up.

In the Standard, we write (I'm omitting some of the template parameters here for brevity and clarity):

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    // exposition only, present only if !forward_range<V>
    iterator_t<V> current_ = iterator_t<V>();
};
```

But we have to write it as something like this:

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    struct empty { };
    using current_t = std::conditional_t<
        !forward_range<V>, iterator_t<V>, empty>;
    [[no_unique_address]] current_t current_ = current_t();
};
```

Just like we saw in the previous section, and perhaps more obviously here, this isn't *really* a conditional member. `current_`, as a member, is always present. It's just that we can concoct a solution that avoids space overhead thanks to `[[no_unique_address]]`.

If we're especially paranoid, we can help ensure that all of these `empty` types are distinct by taking advantage of lambdas:

```cpp
namespace N {
    template <typename T> struct empty_type {
        // add a constructor from anything to make conditional
        // initialization easier to deal with
        constexpr empty_type(auto&&...) { }
    };
}

#define EMPTY_TYPE ::N::empty_type<decltype([]{})>
```

Now, every use of `EMPTY_TYPE` is a distinct type. Which is fine, because the only time we'd use such a thing is here:

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    using current_t = std::conditional_t<
        !forward_range<V>, iterator_t<V>, EMPTY_TYPE>;
    [[no_unique_address]] current_t current_ = current_t();
};
```

But `current_` is still _always_ present. It's not really a conditional member, only its type is conditional. In my experience with needing conditional members at least, having an empty placeholder has been thankfully sufficient.

But there is a case where we really need the member to be truly conditional, and that is...


## Conditional Member Types

The most familiar example of needing a conditional type in C++ is one that I've already hinted at earlier: `std::enable_if`. `enable_if` is nothing more than wanting a type that's either there, or not. If we were specifying it Ranges-style, we'd write it this way:

```cpp
template <bool B, typename T>
struct enable_if {
    using type = T; // present only if B is true
};
```

Here, it's critical that `enable_if<false, T>` has no member `type` at all. Not has a member `type` that is `void` or some other implementation-defined type. No type at all!

![Edna Mode](/assets/edna_mode.jpg)

There is only one way to do this in the language today, which is partial specialization of class templates. You have to do it this way:

```cpp
template <bool B, typename T>
struct enable_if {
    using type = T;
};

template <typename T>
struct enable_if<false, T> { };
```

Or the reverse - have the partial specialization handle the `true` case. Either way.

For a utility like `enable_if`, writing this across multiple specializations isn't that big a deal. Mildly tedious at best. But once you start writing bigger utilities, this becomes a lot more than mildly tedious. Suddenly you have to come up with a crazy workaround.

One of the many new range adaptors in C++23 will be `zip_transform`. Some languages call this `zip_with`: this is a `zip` that additionally takes a function that gets applied to each corresponding argument in all the ranges. For example:

```cpp
vector v1 = {1, 2};
vector v2 = {4, 5, 6};

fmt::print("{}\n", views::zip_transform(plus(), v1, v2)); // [5, 7]
```

Now, if you look at the specification for the iterator (in [\[range.zip.transform.iterator\]](http://eel.is/c++draft/range.zip.transform.iterator)), you'll see that its `iterator` has a member type, `iterator_category`, that is only conditionally present:

```cpp
template <copy_­constructible F, input_­range... Views>
    requires /* ... */
template <bool Const>
class zip_transform_view<F, Views...>::iterator {
    // ...
public:
    using iterator_category = see below; // not always present
    // ...
}
```

The definition of `iterator_category` is complicated (see [\[range.zip.transform.iterator\]/1](http://eel.is/c++draft/range.zip.transform.iterator#1)). But importantly it's only present if all the underlying ranges are forward ranges. And then, when it is present, it's just basically the common category of all the underlying ranges. The wording is a bit involved here, but the underlying operation isn't that complex.

So... how do you do that?

We need the same kind of logic as with `enable_if`,  we need a partial specialization. We can start by thinking of it this way:

```cpp
template <bool B, typename T>
struct maybe_iterator_category {
    using iterator_category = T;
};


template <typename T>
struct maybe_iterator_category<false, T> { };
```

However, the nuance here is that you cannot check for the underlying ranges' `iterator_category` types until we very that they even have them - which means we have to delay evaluation of those traits. The way I implemented this in my approach to `zip_transform` when Tim Song was working on the paper ([P2321](https://wg21.link/p2321)), was to instead take a page out of [Boost.Mp11](https://www.boost.org/doc/libs/develop/libs/mp11/doc/html/mp11.html)'s book:

```cpp
template <bool B, template <typename...> class F, typename... T>
struct maybe_iterator_category {
    using iterator_category = F<T...>;
};

template <typename T>
struct maybe_iterator_category<false, T> { };
```

Which I [used like so](https://godbolt.org/z/df7dTj4nM) (this is on lines 713-729):

```cpp
template <typename T> using nested_iterator_category = typename T::iterator_category;
template <typename I> using iterator_category_for = mp_eval_or<std::input_iterator_tag, nested_iterator_category, iterator_traits<I>>;
template <bool Const> using categories = mp_list<iterator_category_for<iterator_t<maybe_const<Const, Views>>>...>;
template <bool Const, typename Tag> using all_categories_derive_from = mp_all_of_q<categories<Const>, mp_bind_front<is_base_of, Tag>>;

template <bool Const> using result_type = invoke_result_t<maybe_const<Const, F>&, range_reference_t<maybe_const<Const, Views>>...>;

template <bool Const>
class iterator : public maybe_iterator_category<
    // only present if Base models forward_range
    forward_range<maybe_const<Const, InnerView>>,
    mp_cond,
        mp_bool<!is_lvalue_reference_v<result_type<Const>>>,            input_iterator_tag,
        all_categories_derive_from<Const, random_access_iterator_tag>,  random_access_iterator_tag,
        all_categories_derive_from<Const, bidirectional_iterator_tag>,  bidirectional_iterator_tag,
        all_categories_derive_from<Const, forward_iterator_tag>,        forward_iterator_tag,
        mp_true,                                                        input_iterator_tag>
{
    // ...
};
```

There are other slightly different approaches, but they all basically have to jump through the same hoops. You have to inherit from something in order to properly have a conditional member `iterator_category`. You need to come up with some way to delay checking `T::iterator_category` until after we know that we're a `forward_range` (I chose to do this by instead using `std::input_iterator_tag` as the default if there is no `iterator_category` - this default will never be used, but it allows me to write all the conditions in-line, although it makes all the conditions more complex).

But this is basically the only way to really have a true _conditional_ member in C++: you have to inherit from either a type that has that member or a type that does not have that member. I didn't show this in the original example with `Ptr` as an alternative implementation, you could do that too:

```cpp
template <typename T>
struct PtrBase { };

template <typename T> requires (!std::is_void_v<T>)
struct PtrBase {
    auto operator*() const -> T&;
};

template <typename T>
struct Ptr : PtrBase<T>
{ };

Ptr<void> p; // ok
```

And the reason I didn't show this, or indeed consider this a real viable alternative, is that it's... a pretty bad alternative. It's very verbose and disruptive to comprehension (and this even without dealing with how do you implement `PtrBase`'s `operator*`?). In the `Ptr<T>` case, I didn't actually _need_ `operator*` to be truly absent, I just needed to delay instantiation of `operator*`. But in the `zip_transform<F, V...>::iterator` case, I do actually _need_ `iterator_category` to be truly absent.

So inheriting from a conditional base class it is.

It's worth noting here that inheriting from a conditional base class is how we used to have to do conditional member variables as well, if you wanted to avoid the storage overhead. If you look at the paper that gave us `[[no_unique_address]]` ([P0840R0](https://wg21.link/p0840r0)), the tool that lets us avoid the conditional base shenanigans when we're dealing with conditional member variables, the paper clearly points out one huge downside of the original approach:

> Implementation awkwardness: [Empty Base Optimization] requires state that would naturally be represented as a data member to be moved into a base class.

Awkardness indeed.

## An alternate approach

If we look back on these problems, we used three different language features to handle them:

* conditional member variable: `[[no_unique_address]]` with `std::conditional_t` (and if we're really insistent, unevaluated lambdas).
* conditional member function: concepts.
* conditional member type: inheriting from conditional base classes.

Of these, only the last option actually handles all the cases, and only the last option gives you truly a conditional member. It's also the most inconvenient/awkward/tedious/insert pejorative of your choice.

However, D gives us what I think is a clear answer for how we could do conditional members in a way that is properly conditional and avoids the kind of tedium that we have to deal with today: `if`.

We could just use `if` at class scope to declare a conditional member function (no need to come up with a workaround to wrap `T&`):

```cpp
template <typename T>
struct Ptr {
    if (!std::is_void_v<T>) {
        auto operator*() const -> T&
    }
};
```

We could just use `if` at class scope to declare a conditional member variable (no need to come up with a workaround for how to declare the type of `current_` such that it's empty, we can directly use the type that we want for the member everywhere - including its initializer):

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    if (!forward_range<V>) {
        iterator_t<V> current_ = iterator_t<V>();
    }
};
```

And, most significantly, we could just use `if` at class scope to declare a conditional member type:

```cpp
template <typename F, typename... Vs>
struct zip_transform_view<F, Vs...>::iterator {
    if ((forward_range<Vs> && ...)) {
        if (/* not a reference */) {
            using iterator_category = std::input_iterator_tag;
        } else {
            // here we can eagerly access all of the iterator_category's because
            // we know that they exist (because of forward_range)
            using iterator_category = std::common_type_t<
                std::random_access_iterator_tag,
                typename iterator_traits<iterator_t<Vs>::iterator_category...
                >;
        }
    }
};
```

Now here we of course run into the scope problem. `if` introduces a scope, so all of these code fragments look very much like they're introducing something which only exist in the scope in which it's declared (which would then be, at best, a completely pointless exercise). It'd be important to work through the rules of what it actually means to introduce these names and members in these contexts, which will, I'm sure, be subtle and full of dark corners. And while I think that here, a scope-less `if` would be valuable, I still don't feel that `if constexpr` is missing much for introducing a scope (indeed, quite the opposite).

The direction for reflection ([P2237](https://wg21.link/p2237), [P2320](https://wg21.link/p2320)) does offer something like this. The syntax is a work in flight, but would replace this example I just showed:

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    if (!forward_range<V>) {
        iterator_t<V> current_ = iterator_t<V>();
    }
};
```

with something like this (at some point I think the injection operator changed from `<<` to `<-` but I can't find that in the paper, and in any case the specific syntax here is less important than the overall shape of the solution, which I think is about right):

```cpp
template <input_range V>
struct lazy_split_view<V>::outer_iterator {
    consteval {
        if (!forward_range<V>) {
            << <struct { iterator_t<V> current_ = iterator_t<V>(); }>;
        }
    }
};
```

There are a few new things that are new here: a `consteval` block, a code fragment (the `<struct ... >` part), and an injection statement. And this allows for clear definitions of when things happening (in particular, at the end of a `consteval` block, all the fragments queued for injection are actually injected). There's certainly value in having a clear model for things, especially in an area with as much subtlety as this.

I want to be clear that the reason I dislike the `consteval` block approach is not _because_ it's more verbose. It is, but not by a lot. And certainly if I had a choice between the latter and nothing I would choose the latter in an instant. We often talk about verbosity, but I think terseness is only especially important in a few key circumstances (like [lambdas]({% post_url 2020-06-18-lambda-lambda-lambda %})) - and oftentimes terseness is the wrong goal and can significantly harm readability and adoption (c.f. build2). Here the problem isn't strictly that the `consteval` block approach is longer - the problem for me is that none of the additional syntax actually adds meaning on top of the shorter version that's just the `if` statement. The `if` approach isn't just terser for the sake of terseness, and I didn't get there by introducing some grawlix punctuation. It's just the same kind of `if` that we're already familiar with - just in a different context.

As a result I'm hard-pressed to see why we can't just... make the former example mean the latter example. Which would allow us to just have conditional members the same way we write all of our other conditions: with `if`. This isn't to say the `consteval` block approach isn't useful, it certainly is (such as wanting to write a function that returns a code fragment, and inject that - you need some kind of thing to be able to return from such a function, and this is important). Just that the simple case probably merits avoiding some of the ceremony.

Regardless, we do need a better way to express conditional members than what we have today. This isn't that rare a problem, and currently we take very different approaches based on the kind of member we're conditioning, each of which has different nuances and issues.
