---
layout: post
title: "Niebloids and Customization Point Objects"
category: c++
tags:
  - c++
  - c++20
  - ranges
---

C++20 Ranges bring with them several new ideas by way of solving a lot of different problems.

Two of the new terms in Ranges, _niebloids_ and _customization point objects_ (or CPOs), are very frequently confused and used interchangeably. This confusion is pretty understandable (the two are pretty similar, and we don't even have a language mechanism to implement them differently so the fact that they are different at all is more specification handwaviness than actual implementation difference), but the two exist to solve different problems and apply to different parts of the library.

I wanted to take the time here to elaborate on the differences and hopefully alleviate some confusion.

## Customization Point Objects Solve Customization Dispatch

There are a few problems in the ADL-based customization point space.

First, we have this problem where if you want to `swap` two objects, there is a very specific incantation you have to use:

```cpp
// wrong, might not even find a candidate
swap(a, b);

// wrong, might not find customization point
std::swap(a, b);

// correct, but painful
using std::swap; swap(a, b);
```

What customization point objects do is wrap the customization dispatch in a single object. So that you don't have to do any of this:

```cpp
// correct
std::ranges::swap(a, b);

// same thing, just as correct
using namespace std::ranges;
swap(a, b);
```

A second problem with the two step isn't just that it's Yet Another C++ Incantation. If ADL lookup finds a user-provided function, that function gets called and that's that. We don't have the ability to actually _check_ that the user-provided function is correct. What if the user provided `begin(e)` but that's actually a `void` function that starts some execution context and has nothing to do with ranges at all? We don't want to pick that up! Customization point objects also allow you to  impose constraints checking in all cases.

In the standard library, [customization point object](http://eel.is/c++draft/customization.point.object#def:customization_point_object) is a specific term of art that is a semiregular, function object that is const-invocable. And the standard library has a whole bunch of them in the `std::ranges` namespace (`begin`, `end`, `swap`, etc.) but even a few in plain old `std` (e.g. `strong_order`).

One bonus point of confusion here: customization point objects aren't always customizeable! For instance, `std::ranges::cbegin` has no customization point `cbegin` that it tries to invoke; it only ever calls `begin`.

For more, see [N4381](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2015/n4381.html).

## Niebloids solve undesired ADL

While the term "customization point object" appears in the standard, the term "niebloid" does not. Instead, we have [this text](http://eel.is/c++draft/algorithms#requirements-2):

> The entities defined in the std​::​ranges namespace in this Clause are not found by argument-dependent name lookup ([basic.lookup.argdep]).
When found by unqualified ([basic.lookup.unqual]) name lookup for the postfix-expression in a function call ([expr.call]), they inhibit argument-dependent name lookup.

The problem here is completely unrelated to the problem that we need customization point objects for. Let's take one of the simpler algorithms, `std::copy`. For C++98 through C++17, we had this overload (I'm ignoring the parallel one):

```cpp
template<class InputIterator, class OutputIterator>
constexpr OutputIterator copy(InputIterator first, InputIterator last,
                              OutputIterator result);
```

Easy, familiar. But consider the return type. `copy` by definition has to go through the entire input range, yet it doesn't return the end _input_ iterator, only the new _output_ iterator. This is okay in C++17 where we have iterator pairs, since you already by definition have the end input iterator. But once C++20 comes around, we might not actually have the end input iterator, we might only have a sentinel. For example:

```cpp
struct zstring_sentinel {
    bool operator==(char const* p) const {
        return *p == '\0';
    }
};

void copy_string(char const* src, char* dst) {
    std::ranges::copy(some_ptr, zstring_sentinel{}, dst);
}
```

This works fine. In the process of copying this null-terminated string, we also do find the null terminator. But then we throw it away, even though that would be useful information that took work to compute! This is why the C++20 ranges overloads look different:

```cpp
  namespace ranges {
    // basically a pair
    template<class I, class O>
      using copy_result = in_out_result<I, O>;

    template<input_iterator I, sentinel_for<I> S, weakly_incrementable O>
      requires indirectly_copyable<I, O>
      constexpr copy_result<I, O>
        copy(I first, S last, O result);
        
    template<input_range R, weakly_incrementable O>
      requires indirectly_copyable<iterator_t<R>, O>
      constexpr copy_result<borrowed_iterator_t<R>, O>
        copy(R&& r, O result);
  }
}
```

This is a pretty nice improvement, allowing us to both copy and find the end input iterator in one go. But we have this problem, what happens when we do:

```cpp
using namespace std::ranges;

copy(first, last, result);
```

Which overload gets called? If none of `first`, `last`, or `result` have `std` as an associated namespace, then this is easy: we only have one possible candidate anyway (well, I guess two if you include the `std::ranges::copy` overload that takes a range, but it only takes two parameters, so it's no kind of viable).

However, what happens if we _do_ have `std` as an associated namespace? Now things get a little trickier. If `first` and `last` have different types, then `std::copy` couldn't be a viable candidate, so we'd still call `std::ranges::copy`. But if `first` and `last` have the _same_ type (i.e. this is "common" range), then we would call `std::copy`! Because it's more specialized!

This is easier to see if strip some information and put them closer together:

```cpp
template <typename T>
void f(T, T); // approximately std::copy

template <typename T, typename U>
    requires something<T, U>
void f(T, U); // approximately std::ranges::copy
```

"More specialized" as a tiebreaker precedes "more constrained". 

The consequence of this is that seemingly innocuous code like:

```cpp
template <typename R>
void f(R&& r) {
    using namespace std::ranges;
    
    // intent is to use std::ranges::copy
    auto [i, o] = copy(v.begin(), v.end(), somewhere);
}
```

May or may not compile. Moreover, if `r` is a type as exotic as `std::vector<int>`, then whether or not the above works is entirely implementation-defined. If `std::vector<int>::iterator` is `int*` (entirely allowed), then the above is fine (ADL wouldn't find `std::copy`). But if `std::vector<int>::iterator` is, say, `__gnu_cxx::__normal_iterator<int*, std::vector<int> >` (as it is in libstdc++), then the above is broken.

This is quite bad.

We definitely want to ensure that whenever this works:

```cpp
std::ranges::some_algo(first, last, args...);
```

That this also works _and does the same thing_:

```cpp
using namespace std::ranges;
some_algo(first, last, args...);
```

Unfortunately, if we implemented `std::ranges::copy` as two overloaded function templates, we could not stop this from happening. We're, basically, doomed. While this is especially bad for `copy` where the return type changes, it's also not ideal for algorithms like `find` or `any_of` where even though the return type is the same, it's still surprising that the two formulations can call different functions entirely. 

However, ADL only kicks in if the initial unqualified lookup either found nothing or found functions or function templates. If unqualified look finds an _object_, no ADL happens. So if instead of declaring:

```cpp
namespace ranges {
    template<input_iterator I, sentinel_for<I> S, weakly_incrementable O>
      requires indirectly_copyable<I, O>
      constexpr copy_result<I, O>
        copy(I first, S last, O result);
        
    template<input_range R, weakly_incrementable O>
      requires indirectly_copyable<iterator_t<R>, O>
      constexpr copy_result<borrowed_iterator_t<R>, O>
        copy(R&& r, O result);
}
```

we declared:

```cpp
namespace ranges {
    struct copy_fn {
        template<input_iterator I, sentinel_for<I> S, weakly_incrementable O>
            requires indirectly_copyable<I, O>
        constexpr copy_result<I, O>
            operator()(I first, S last, O result) const;
        
        template<input_range R, weakly_incrementable O>
            requires indirectly_copyable<iterator_t<R>, O>
        constexpr copy_result<borrowed_iterator_t<R>, O>
            operator()(R&& r, O result) const;
    };
    
    inline constexpr copy_fn copy{};
}
```

Then we have no problem. `std::ranges::copy` and `using namespace std::ranges; copy` both find that object and lookup stops. Problem solved.

But... we don't want to specify algorithms as overload function call operators. We want to specify algorithms as, well, algorithms. As functions. So we insert this wording about how magically all of these functions inhibit ADL, so that we can have sane specification. Even though our _only_ current language mechanism for living up to this specification is to make them objects. 

And indeed, the `ranges::copy` I wrote there meets the criteria for a _customization point object_. It's just... not actually a customization point object, because we just don't want to call it an object. We want to call it a function.

So it became a niebloid.

It's possible that a future language feature might come around that would allow us to explicitly opt functions and functions templates out of ADL. This would allow an implementation strategy like:

```cpp
namespace ranges {
    template<input_iterator I, sentinel_for<I> S, weakly_incrementable O>
        requires indirectly_copyable<I, O>
      no_adl constexpr copy_result<I, O>
        copy(I first, S last, O result);
        
    template<input_range R, weakly_incrementable O>
        requires indirectly_copyable<iterator_t<R>, O>
      no_adl constexpr copy_result<borrowed_iterator_t<R>, O>
        copy(R&& r, O result);
  }
}
```

For instance, Matt Calabrese's [Customization Point Functions](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1292r0.html) proposal would allow you to declare a function `final` to get this desired ADL-inhibiting behavior.

And the specification is written in a way to allow such future language evolution without having to change anything. Indeed, it is within the implementation purview today for GCC to do something like add a `__gcc_no_adl` specifier that itself magically inhibits ADL and ends up with `std::ranges::copy` not being an object (although they do not do that today). Which means that while:

```cpp
auto f = std::ranges::begin;
```

is specified to be valid code, the same is not true for:

```cpp
auto g = std::ranges::copy;
```

Because `std::ranges::copy` need not actually be an object (though, again, that's the only standard implementation strategy) and even if it were an object, it need not actually be copyable.

See also [STL2 Issue #371](https://github.com/ericniebler/stl2/issues/371). I thought I had read about this in a paper or blog at some point, but I can't seem to find one at the moment.

## Niebloids vs Customization Point Objects

In short:

- a _customization point object_ is a semiregular, function object (by definition) that exists to handle constrained ADL dispatch for you. `ranges::begin`, `ranges::swap`, etc, are customization point objects.

- a _niebloid_ is a colloquial name for the algorithms declared in `std::ranges` that inhibit ADL. The only implementation strategy in standard C++20 for them is to make them function objects, but they are not required to be objects at all (nor are they required to be copyable, etc.) and a possible future language extension would allow them to be implemented as proper function templates. 

These terms are completely disjoint - they refer to different parts of the library and exist as solutions to different problems. A niebloid is not a customization point object (nor even required to be an object), a customization point object is not a niebloid (although, since it is an object, it does also inhibit ADL). 

The More You Know.