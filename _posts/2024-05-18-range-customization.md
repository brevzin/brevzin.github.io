---
layout: post
title: "Are we missing a Ranges customization point?"
category: c++
tags:
  - c++
  - ranges
---

Let's say we're writing one container that we're implementing in terms of another container. If we want to make my container a range based entirely on that other container, that's easy:

```cpp
template <typename T>
class StableVector {
    std::vector<T*> impl;

public:
    auto begin() const { return impl.begin(); }
    auto end() const { return impl.end(); }
};
```

However, let's say we don't want to make `StableVector<T>` behave exactly like `std::vector<T*>`. As the name might suggest, we want it to be a range of `T` (where the underlying `std::vector` is an implementation detail), not a range of `T*`. So what do we do?

## C++20 Ranges?

This is where Ranges can help us out. If we have an object of type `StableVector<T>` we can adapt it the way we want:

```cpp
sv | views::transform(*_1)
```

This is using Boost.Lambda2, which is a delightfully terse way of expressing this simple idea (now also proposed as [P3171](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2024/p3171r0.html)), but obviously isn't the only way to spell that function.

But I didn't say that I want the _user_ of `StableVector<T>` to be able to do this adaption. I want me, as the _author_ of `StableVector<T>` to do it (so that users don't have to).

Here's where you might think we can just write this:

```cpp
template <typename T>
class StableVector {
    std::vector<T*> impl;

public:
    auto begin() const { return views::transform(impl, *_1).begin(); }
    auto end() const { return views::transform(impl, *_1).end(); }
};
```

After all, we have a range adaptor, so we just adapt our range and pull out the iterators. Right?

This unfortunately doesn't work. We're returning iterators into two different views, and the views go out of scope before we even finish returning those iterators. There _are_ some types for which this is okay, but `views::transform` isn't one of them.

> That category of types is called borrowed ranges.
{:.prompt-info}

Moreover, even if `views::transform` happened to be a borrowed range, the problem we're describing is a general pattern so you could simply replace the `transform` with another adaptor (or sequence of adaptors) of your choice.

So C++20 ranges are no help for this particular problem.

## Boost.Ranges?

While adapting _ranges_ is typically [significantly] better than adapting iterators, this is one case where adapting iterators is what we would actually need. The C++ Standard Library doesn't really have a lot of _iterator_ adaptors though (just a few, like `move_iterator`, `reverse_iterator`, etc.). The range adaptors' iterator types tend to have exposition-only, private constructors that are only intended for use by their respective ranges. So we can't simply use `ranges::iterator_t<ranges::transform_view<V, F>>` here since we wouldn't know how to construct it. And even if you could construct it, they wouldn't work anyway, since many of the iterators keep pointers to their parent range to stash various state that they need (like the one we need for this problem).

Boost originally had a set of adapted iterators, and that set included `transform`. So we could use that one here:

```cpp
template <typename T>
class StableVector {
    std::vector<T*> impl;

public:
    auto begin() const { return boost::make_transform_iterator(impl.begin(), *_1); }
    auto end() const { return boost::make_transform_iterator(impl.end(), *_1); }
};
```

This works.

But it's a bit unsatisfying because we just have to repeat ourselves. This sort of thing is precisely why we adopted range adaptation as the main model rather than iterator adaptation, since iterator composition is exceedingly tedious.

Moreover, the Boost adapted iterator set wasn't that big. It has a some of the very useful ones (e.g. `transform`, `filter`, `zip`) but many of the more complicated range adaptors that we've added in C++20, C++23, and C++26 don't have Boost analogs. You're back to writing your own, despite the Standard Library seemingly catering to your needs.

## What are we missing?

The problem here is, ultimately, that it's easy to pass-through one thing but it's hard to pass-through two things. It's again why ranges are easier to deal with than iterators.

In Rust's iteration model, for instance, there is just *one* function that gives you the iterator (`into_iter` on the `IntoIterator` trait) rather than two, so wrapping it to do whatever complex thing you want isn't a problem - because you only have to write it one time. But in C++, both the library (by way of ranges) and the language (by way of the range-based for loop) simply require two parts: a `begin` and an `end`. Those two functions just can't both depend on a common intermediate state.

But what if that wasn't the case? What if you _could_ depend on a common intermediate state?

The range-based for loop right now desugars this loop:
```cpp
for (auto e : r) {
    // body
}
```
into, roughly, this loop:
```cpp
{
    auto&& range = r;     // C++23: all temporaries are lifetime-extended
    auto b = range.begin();
    auto e = range.end(); // C++17: allowed e to be a different type from b
    for (; b != e; ++b) {
        auto e = *b;
        // body
    }
}
```

What if we added another step into that mix:

```diff
{
    auto&& __range = r;   // C++23: all temporaries are lifetime-extended
+   auto&& range = INTO_RANGE(__range);
    auto b = range.begin();
    auto e = range.end(); // C++17: allowed e to be a different type from b
    for (; b != e; ++b) {
        auto e = *b;
        // body
    }
}
```

Where `INTO_RANGE(x)` will keep calling `x.into_range()` on `x` until it finds something that is a range (similarly to how `operator->()` will keep calling `operator->()` until it finds something that is a pointer).

That would allow this simple implementation of `StableVector<T>`:

```cpp
template <typename T>
class StableVector {
    std::vector<T*> impl;

public:
    auto into_range() const { return views::transform(impl, *_1); }
};
```

At least, that'd be the goal. Figuring out how to actually make this work is something else entirely.

## What's so hard about this?

Right now, the `std::ranges::range` concept is defined as a type on which you can call `ranges::begin` and `ranges::end`.

Would we want to extend `StableVector<T>` to be a `range` in this sense, by having `ranges::begin` try to call `into_range()`? No! Because then every range algorithm in the wild which does something like this:

```cpp
template <std::ranges::input_range R>
auto some_algo(R&& r) -> void {
    auto first = std::ranges::begin(r);
    auto last = std::ranges::end(r);
}
```

would end up evaluating as:

```cpp
template <typename T>
auto some_algo(StableVector<T> const& sv) -> void {
    auto first = sv.into_range().begin();
    auto last = sv.into_range().end();
}
```

and now we're just back to our very first buggy implementation with two dangling iterators into two, different, already destroyed `transform_view`s.

What would have to happen instead is that every algo would have to add another overload:

```cpp
// the actual implementation
template <std::input_iterator I, std::sentinel_for<I> S>
auto some_algo(I, S) -> void;

// the one that everyone calls
template <std::ranges::input_range R>
auto some_algo(R&& r) -> void {
    some_algo(std::ranges::begin(r), std::ranges::end(r));
}

// and this new one
template <std::ranges::into_range R>
auto some_algo(R&& r) -> void {
    // a new customization point object that would repeatedly call into_range()
    some_algo(std::ranges::into_range(r));
}
```

And then the range adaptors have the same problem. Something like `views::transform(E, F)` would have to first dispatch to `views::transform(ranges::into_range(E), F)`. I haven't thought about this too much, but I suspect there are other thorny lifetime questions that come up here too.

## Is this worth doing?

It's an unfortunate problem. Because Range customization in C++ has always been a two-function operation - you always need `begin()` and `end()` - that makes it infeasible to defer implementing a type's range implementation to some sequence of range adapters. The only real way to do this is with iterator adaptors, which mostly don't exist in the Standard Library. Boost has some, but not a lot.

However, figuring out how to make something like the `into_range` approach I sketched actually work seems... a bit daunting. I'm mostly hoping there's some clever solution to this problem that I haven't thought of.

Incidentally, this is another example of the [coercing problem]({% post_url 2021-09-10-deep-const %}) I wrote about some years ago. In that blog post, I wanted to write these two algorithms:

```cpp
template <typename T>
void takes_generic_const_span(span<T const>);

template <constant_range R>
void takes_any_range(R&&);
```

Where the first one actually _coerces_ any incoming contiguous and sized range to be a `span` (rather than being a nearly useless function template) and the second one actually _coerces_ any incoming range to be a `constant_range` (by way of `views::as_const`). You can achieve both today in ways the blog post demonstrates, but it's something you have to learn and you have to repeat for every algorithm you write.

In the same way, this `into_range` problem is a coercing problem: ideally any algorithm that accepts a `range` could just coerce any type that provides a suitable `into_range` member function into a `range`, without having _every_ algorithm write the boilerplate overload to do so.

I don't know how to make that work either.

And in the end, I can just write `into_range()` and make users write `sv.into_range()` when that's what they want to do. Perhaps they don't even need range facilities often enough for it to be more than a minor nuisance.
