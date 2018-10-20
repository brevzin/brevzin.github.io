---
layout: post
title: "Higher Order Fun"
category: c++
tags:
 - c++
 - c++17
 - c++20
--- 

... in C++.

That seems like a fundamentally wrong statement to make right? C++ has been greatly improving over the last few standards in its direct support for a more functional style of programming. But it’s still much more verbose than necessary to write a simple lambda, it’s surprisingly tricky to write a function that accepts a function, and it’s obnoxious at best to pass a function into a function if you happen to use templates, overloads, or default arguments.

I’m hoping to get much better language support for all three of these in the future (having actively spent time on the first of these), but until then... there is a new Boost library by Paul Fultz II that at least gives us a lot of tools that make some of these problems easier: [Boost.HOF](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/doc/index.html#) (which stands for higher-order functions). This is a library that comes with a lot of handy tools for building more complicated functions out of simple functions — and to me personally, this is the kind of programming that just feels really fun to do because of how elegant these sorts of things end up being.

I wanted to go through two problems and how I would implement them with HOF just to show what I mean.

<hr />

Let’s start with `<=>`. I’ve previously written about how to [implement `<=>`](https://medium.com/p/implementing-the-spaceship-operator-for-optional-4de89fc6d5ec) for a class, but here I’m going to approach a different problem: implementing `compare_3way()`. This is a library helper that needs to be used when you implement `<=>` for your own types, and to be used in other algorithms that require three-way comparisons (as a quick aside — I think this particular function is wrong and needs to not exist, see [P1186](https://wg21.link/p1186).

`compare_3way(a,b)` is defined in terms of trying to do different operations and falling back until it fails. Just copying the wording from [alg.3way]:

1. Returns `a <=> b` if that expression is well-formed.
2. Otherwise, if the expressions `a == b` and `a < b` are each well-formed and convertible to `bool`, returns `strong_ordering​::​equal` when `a == b` is `true`, otherwise returns `strong_ordering​::​less` when `a < b` is `true`, and otherwise returns `strong_ordering​::​greater`.
3. Otherwise, if the expression `a == b` is well-formed and convertible to `bool`, returns `strong_equality​::​equal` when `a == b` is `true`, and otherwise returns `strong_equality​::​nonequal`.
4. Otherwise, the function is defined as deleted.

Think about how you would try to implement this using whatever tricks you have at your disposal. It’s tempting to start off with a chain of `if constexpr`s but getting to #4 you get kind of stuck. You need a failure case of some sort, and you can’t use something like static_assert here because the failure needs to be externally detectable. Personally, my go-to solution comes from Xeo’s article: [Beating overload resolution into submission](https://blog.rmf.io/cxx11/overload-ranking). Great read.

I’m not going to post that solution here - instead I’m going to do this purely with higher-order functions. Let’s build our final function up from small pieces.

Step #1. How would we write that? We need a function that takes two arguments (of possibly different types) and just returns the result of `<=>` if that’s valid. That’s just standard trailing-return-type based SFINAE:

```c++
auto step1 = [](auto const& a, auto const& b) -> decltype(a <=> b) {
    return a <=> b;
};
```

Except I don’t like repeating things. It’s very common to want to write a lambda that just returns a particular expression but is constrained on that expression being valid. This was the primary motivation for [P0573](https://wg21.link/p0573). Many people have their own macro especially for this case. In Boost.HOF, it’s spelled [`BOOST_HOF_RETURNS`](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/include/boost/hof/returns.html):

```c++
auto step1 = [](auto const& a, auto const& b)
    BOOST_HOF_RETURNS(a <=> b);
```

Step #2. How would we write *just* the second part? Let’s not worry about the fall-back procedure yet. Let’s just write the correct body and the correct constraints. Since we’re writing a function that’s only meaningful for `<=>`, we might as well use all of C++20, including Concepts. Concepts make writing this constraint much easier, even with slightly simplified `concept`s for the ordering constraints (I’m focusing here on playing with functions and less on correct concept writing). Indeed, Step #3 is roughly the same as Step #2 so let’s put them both together:

```c++
template <typename T, typename U>
concept EqualityComparable = requires(T const& a, U const& b) {
    { a == b } -> bool;
};

template <typename T, typename U>
concept Ordered = EqualityComparable<T, U> &&
    requires(T const& a, U const& b) {
        { a < b } -> bool;
    };

auto step2 = [](auto const& a, auto const& b) -> strong_ordering
    requires Ordered<decltype(a), decltype(b)>
{
    if (a == b) return strong_ordering::equal;
    if (a < b) return strong_ordering::less;
    return strong_ordering::greater;
};

auto step3 = [](auto const& a, auto const& b) -> strong_equality
    requires EqualityComparable<decltype(a), decltype(b)>
{
    if (a == b) return strong_equality::equal;
    return strong_equality::nonequal;
};
```

Ok great. We have our three steps, how do we put them together? What we need is to order these steps so that the first one that works gets executed and, if none of them work, nothing gets called in a way that is SFINAE-friendly.

Turns out, there’s an app for that in Boost.HOF. It is called [`first_of`](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/include/boost/hof/first_of.html). All we need to do is pass in our functions, which we’ve already created, and we’re... done:

```c++
template <typename T, typename U>
concept EqualityComparable = requires(T const& a, U const& b) {
    { a == b } -> bool;
};

template <typename T, typename U>
concept Ordered = EqualityComparable<T, U> &&
    requires(T const& a, U const& b) {
        { a < b } -> bool;
    };

constexpr inline auto compare_3way = boost::hof::first_of(
    // step #1: <=>
    [](auto const& a, auto const& b)
        BOOST_HOF_RETURNS(a <=> b),
    // step #2: == and <
    [](auto const& a, auto const& b) -> strong_ordering
        requires Ordered<decltype(a), decltype(b)>
    {
        if (a == b) return strong_ordering::equal;
        if (a < b) return strong_ordering::less;
        return strong_ordering::greater;
    },
    // step #3: just ==
    [](auto const& a, auto const& b) -> strong_equality
        requires EqualityComparable<decltype(a), decltype(b)>
    {
        if (a == b) return strong_equality::equal;
        return strong_equality::nonequal;
    }
);
```

Too bad there’s no compiler yet that implements `<=>` so I can’t check it, but outside of typos, this is probably right.

That’s a remarkably small amount of code to do a fairly complex thing. Note that the failure case is automatically handled for us. If we run out of functions in the list for `first_of`, we just have no function left.

Hopefully that’s a nice demo of what higher order functions can do for you. We got three small, simple pieces - and just put them together.

<hr />

Now let’s go wild. One problem that everyone runs into sooner or later with C++ is that passing functions to other functions is hard. You sometimes want to pass in a function that happens to be a template, or happens to have a default argument, or maybe is part of an overload set, or can only be found with ADL... and in all those cases, just passing in `foo` isn’t going to cut it. In the worst case, you do manual overload resolution yourself on which `foo` you had intended to call, which possibly involves doing template deduction by hand too. The better way to do it is to write a macro which lifts your name into a function object that you can actually pass around. In Boost.HOF, this is [`BOOST_HOF_LIFT`](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/include/boost/hof/lift.html). This handles most of the cases you will run into.

But not all the cases. There is one case that I wanted to walk through here, which is this: I want to call a member function (that is a template or overloaded or ...), but either the class instance will be passed into me (so I can’t just write `BOOST_HOF_LIFT(obj.mem)` or equivalent) or I do have the class instance but I am getting it from a function that my function object needs to own. The motivation example of the paper proposing [`bind_front()`](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2017/p0356r3.html) is:

```c++
bind_front(&Strategy::process, createStrategy())
```

This function object needs to own the `Strategy` (and not call `createStrategy()` every time!). This works fine if `process` is a simple, non-overloaded, non-template function. But.. what if it’s not? I want to provide something to that first argument of `bind_front` that _just works_.

What do I mean by just works? Let’s call this function `f`. What I want `f(p, a, b, c, ...)` to mean is:

- If `p` is a pointer to `Strategy` or a type derived from `Strategy`, then `p->process(a, b, c, ...)`
- If `p` is a reference to `Strategy` or a type derived from `Strategy`, then `p.process(a, b, c, ...)`
- If `p` is a `reference_wrapper` of `Strategy` or a type derived from `Strategy`, then `p.get().process(a, b, c, ...)`. This one I’ll even extend to any type implicitly convertible to a reference to `Strategy`.
- If `p` is a smart pointer to `Strategy` or an iterator to `Strategy` or any other kind of thing that `p->process(a, b, c, ...)` invokes process on a Strategy, then that.

In other words, this is a fairly complex series of potential behaviors that all kind of sums up to: just do what I mean. We want to support both `Strategy` and `SpecialStrategy`, because that’s how normal function calls work. We want to support pointers and references, because that’s too specific otherwise. And we want to support `unique_ptr<Strategy>` and `vector<Strategy>::iterator` and `reference_wrapper<Strategy>` because we want to be as useful as possible.

Daunting.

As before, let’s just break it down into small pieces. Let’s start with the pointer case. We can’t have the class instance argument be deduced (i.e. have type `auto`) because we want to ensure that we are calling `Strategy::process` and not `SomeOtherThingEntirely::process`. We could deduce a pointer and check that this pointer is convertible to `Strategy const*`, but I’m just going to take the easy road here and write two functions: one for `Strategy*` and one for `Strategy const*`. We could use `first_of` here and ensure that we write the non-const overload first, but these cases are mutually exclusive so we’ll use best-match instead of first-match. In HOF, that is spelled [`match`](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/include/boost/hof/match.html):

```c++
#define FWD(x) static_cast<decltype(x)&&>(x);

auto pointer_case = boost::hof::match(
    [](Strategy* p, auto&&... args)
        BOOST_HOF_RETURNS(p->process(FWD(args)...)),
    [](Strategy const* p, auto&&... args)
        BOOST_HOF_RETURNS(p->process(FWD(args)...))
);
```

Okay, cool. Now, let’s do the reference case. Here, I am deliberately not deducing the class instance argument because I want the reference case to _just work_ for `reference_wrapper`. `reference_wrapper<T>` is implicitly convertible to `T&`, so having the instance argument not be a template parameter allows this conversion to happen.

We need to write out the four cases, which is a bit repetitive. Using `match` instead of `first_of` means we don’t have to carefully reason about what the right order is:

```c++
#define FWD(x) static_cast<decltype(x)&&>(x);

auto ref_case = boost::hof::match(
    [](Strategy& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
    [](Strategy const& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
    [](Strategy&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...)),
    [](Strategy const&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...))        
);
```

So far so good. Now, we’re just left with the smart pointer case. How do we do this one?

What we want to do is say that if `p.operator->()` is a pointer to some kind of `Strategy`, just fall back to the pointer case we already have. In other words, recursively call ourselves. There’s an adapter for that too! It’s called [`fix`](https://www.boost.org/doc/libs/1_68_0/libs/hof/doc/html/include/boost/hof/fix.html). It adapts all of the functions you provide it to take additionally as their first argument the instance of the combined function object. This idea is also known as a Y-combinator, or a fixed-point combinator.

Rather than showing this final step separately, I’m going to show this all put together. Note that the pointer and reference cases gained an extra argument which they do not use:

```c++
constexpr inline auto process = boost::hof::fix(
  boost::hof::first_of(
    // pointer case
    boost::hof::match(
      [](auto, Strategy* p, auto&&... args)
        BOOST_HOF_RETURNS(p->process(FWD(args)...)),
      [](auto, Strategy const* p, auto&&... args)
        BOOST_HOF_RETURNS(p->process(FWD(args)...))
      ),
    // reference case
    boost::hof::match(
      [](auto, Strategy& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
      [](auto, Strategy const& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
      [](auto, Strategy&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...)),
      [](auto, Strategy const&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...))        
    ),
    // smart pointer case
    [](auto self, auto&& this_, auto&&... args)
      BOOST_HOF_RETURNS(self(this_.operator->(), FWD(args)...))
));
```

Now that’s already pretty cool to me. Here’s this fairly complex requirement set that we can just methodically break down into little pieces. We know how to write those little pieces, and we know how to put those pieces together - it’s really the power of higher order functions at how elegant this ends up being.

Indeed, as Paul points out, rather than three cases (pointer, reference, smart pointer), we can simplify this further to only have two cases: reference and dereference:

```c++
constexpr inline auto process = boost::hof::fix(
  boost::hof::first_of(
    // reference case
    boost::hof::match(
      [](auto, Strategy& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
      [](auto, Strategy const& p, auto&&... args)
        BOOST_HOF_RETURNS(p.process(FWD(args)...)),
      [](auto, Strategy&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...)),
      [](auto, Strategy const&& p, auto&&... args)
        BOOST_HOF_RETURNS(std::move(p).process(FWD(args)...))        
    ),
    // dereference case
    [](auto self, auto&& this_, auto&&... args)
      BOOST_HOF_RETURNS(self(*FWD(this_), FWD(args)...))
))
```

Of course, I’m not going to write a 17-line thing whenever I need to do something like this. To make this practical, I will have to resort to writing a macro:

```c++
#define CLASS_MEMBER(T, mem) boost::hof::fix(boost::hof::first_of(  \
    boost::hof::match(                                              \
        [](auto, T& s, auto&&... args)                              \
            BOOST_HOF_RETURNS(s.mem(FWD(args)...)),                 \
        [](auto, T&& s, auto&&... args)                             \
            BOOST_HOF_RETURNS(std::move(s).mem(FWD(args)...)),      \
        [](auto, T const&& s, auto&&... args)                       \
            BOOST_HOF_RETURNS(std::move(s).mem(FWD(args)...)),      \
        [](auto, T const& s, auto&&... args)                        \
            BOOST_HOF_RETURNS(s.mem(FWD(args)...))),                \
    [](auto self, auto&& this_, auto&&... args)                     \
        BOOST_HOF_RETURNS(self(*FWD(this_), FWD(args)...))          \
    ))
```


And now, the motivating example for `bind_front()` becomes:

```c++
bind_front(CLASS_MEMBER(Strategy, process), createStrategy())
```

which works even if process is overloaded, or a function template, or takes default arguments. It works if we pass it a pointer, or a reference, or a smart pointer, or an iterator, or a `reference_wrapper`.

Pretty cool stuff!

<hr />

As a bonus, here is an implementation of `std::invoke()`:

```c++
constexpr inline auto invoke = boost::hof::first_of(
    [](auto&& f, auto&& t1, auto&&... args)
        BOOST_HOF_RETURNS((FWD(t1).*f)(FWD(args)...)),
    [](auto&& f, std::reference_wrapper<auto> t1, auto&&... args)
        BOOST_HOF_RETURNS((t1.get().*f)(FWD(args)...)),
    [](auto&& f, auto&& t1, auto&&... args)
        BOOST_HOF_RETURNS(((*FWD(t1)).*f)(FWD(args)...)),
    [](auto&& f, auto&& t1)
        BOOST_HOF_RETURNS(FWD(t1).*f),
    [](auto&& f, std::reference_wrapper<auto> t1)
        BOOST_HOF_RETURNS(t1.get().*f),
    [](auto&& f, auto&& t1)
        BOOST_HOF_RETURNS((*FWD(t1)).*f),
    [](auto&& f, auto&&... args)
        BOOST_HOF_RETURNS(FWD(f)(FWD(args)...))
);
```

This is basically a literal translation of [\[func.require\]]( http://eel.is/c++draft/function.objects#func.require-1).

Alternatively, we can group the two reference_wrapper cases and the two dereference cases together:

```c++
constexpr inline auto invoke = boost::hof::first_of(
    boost::hof::fix(
      boost::hof::first_of(
        [](auto, auto&& f, auto&& t1, auto&&... args)
          BOOST_HOF_RETURNS((FWD(t1).*f)(FWD(args)...)),
        [](auto, auto&& f, auto&& t1)
          BOOST_HOF_RETURNS(FWD(t1).*f),
        [](auto self, auto&& f, std::reference_wrapper<auto> t1, auto&&... args)
          BOOST_HOF_RETURNS(self(FWD(f), t1.get(), FWD(args)...)),
        [](auto self, auto&& f, auto&& t1, auto&&... args)
          BOOST_HOF_RETURNS(self(FWD(f), *FWD(t1), FWD(args)...))
      )),
    [](auto&& f, auto&&... args)
        BOOST_HOF_RETURNS(FWD(f)(FWD(args)...))
);
```

Here, we can deduce everything, since if we get a pointer to member, the language itself takes care of the fact that we can’t just invoke a pointer to member on the wrong type. My one question here really is about `reference_wrapper<auto>.` I am not sure what the state of Concepts is with respect to that particular feature. If that is not supported, then we’d have to replace those two options (on lines 4 and 10) with a different way of spelling that constraint.

On the one hand, this is super cool. On the other hand, I think `invoke()` as a function shouldn’t be necessary.