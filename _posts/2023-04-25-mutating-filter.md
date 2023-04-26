---
layout: post
title: "Mutating through a filter"
category: c++
tags:
 - c++
 - c++20
 - ranges
pubdraft: yes
permalink: mutating-filter
---

## Introduction

Nico Josuttis gave a talk recently that included an example like this:

```cpp
std::vector<int> coll{1, 4, 7, 10};

auto isEven = [](int i) { return i % 2 == 0; };

// increment even elements:
for (int& i : coll | std::views::filter(isEven)) {
    ++i; // UB: but works
}
```

I wanted to explain what's going on in this example, what the issue is, and what (if anything) is broken.

## Input vs Forward Iterators

As with a lot of my explanations, we have to start from the beginning.

The C++ iterator model has a number of iterator categories: input, forward, bidirectional, random access, and (since C++20) contiguous. This post only needs to consider the first two.

An input range (a range whose iterator is an input iterator) is a single-pass range. You can only even call `begin()` one time on it. You can't have multiple different input iterators into the same range - incrementing one immediately invalidates any existing copies.

{:.prompt-info}
> Postfix increment on an input iterator is a pretty weird operation, since given
> ```cpp
> auto j = i++;
> ```
> If postfix increment returns the same iterator type, `j` is immediately invalidated by the increment of `i`. Not the most useful operation. This is why in C++20, postfix increment on an iterator is allowed to (and should) return `void`. In the old requirements, postfix increment (in order to be valid) could have returned a proxy object that basically holds a reference to `i` - which is just weird.
>
> For similar reasons, input-only iterators are allowed to be non-copyable in C++20.

A forward range is a significant increase in functionality. A forward range is multi-pass, and can have multiple independent iterators into it at any given time.

For instance, consider `min_element`:

```cpp
template <forward_iterator I>
auto min_element(I first, I last) -> I
{
    if (first == last) {
        return last;
    }

    I smallest = first;
    for (++first; first != last; ++first) {
        if (*first < *smallest) {
            smallest = first;
        }
    }

    return smallest;
}
```

If `I` were simply an input iterator, that first increment of `first` would invalidate `smallest`, and the dereference of it would be UB. You need to have a forward iterator in order to allow holding onto `smallest` like this.

There's a number of other consequences of the multi-pass guarantee that we expect of forward iterators. In particular, typically the _position_ of the iterator is independent of the _value_ that it refers to. What I mean by that is that we expect that incrementing two copies of an iterator the same amount of times should get to the same place, regardless of what, if anything, you do with the value:

```cpp
auto j = i;
assert(i == j);
++i;
++j;
assert(i == j);
++i;
func(*i);
++j;
assert(i == j);
```

We expect all of these assertions to hold. In a similar vein, for a bidirectional iterator, incrementing and then decrementing that iterator should get you back to the same place.

For example, let's take an algorithm like `pairwise`. This is now a range adapter in C++23 as well, but I'll stick with the algorithm for simplicity:

```cpp
template <forward_iterator I, class F>
void pairwise(I first, I last, F f) {
    if (first == last) {
        return;
    }

    I next = std::ranges::next(first);
    for (; next != last; ++first, ++next) {
        f(*first, *next);
    }
}
```

As with `min_element`, this requires a forward iterator because we have two, separate iterators that we're advancing at the same time. A sample use of this example:

```cpp
vector<int> v = {1, 2, 3, 4, 5, 6};
pairwise(v.begin(), v.end(), [](int i, int j){
    fmt::println("({}, {})", i, j);
});
```

This prints `(1, 2)`, `(2, 3)`, `(3, 4)`, `(4, 5)`, and then `(5, 6)`.

## What's so special about `filter`?

I said earlier that typically the position of the iterator is independent of its value. One case where this isn't quite true is with a filtered iterator - since the value could very well affect the iterator's position. More concretely, the value could affect whether the iterator has any position at all!

Let's add a filter to our example from earlier:

```cpp
vector<int> v = {1, 2, 3, 4, 5, 6};
auto evens = v | views::filter(is_even);
pairwise(evens.begin(), evens.end(), [](int i, int j){
    fmt::println("({}, {})", i, j);
});
```

This now, as expected, prints [just the even numbers](https://godbolt.org/z/n5Yz1xP4Y), pairwise: `(2, 4)`, and then `(4, 6)`.

But let's do something a little bit odd. Our function took two `int`s before, but we could take `int&`s too. And once we do that, we could throw in some mutation:

```cpp
vector<int> v = {1, 2, 3, 4, 5, 6};
auto evens = v | views::filter(is_even);
pairwise(evens.begin(), evens.end(), [](int& i, int& j){
    fmt::println("({}, {})", i, j);
    ++j;
});
```

This [now prints](https://godbolt.org/z/We444MW8s) `(2, 4)` and then... `(6, 6)`?? That's pretty weird! What happened to our two independent iterators referring to different elements? Suddenly `first` caught up with `next`?

What happened here is that we changed the `4` to no longer satisfy the predicate (`is_even`). This means we changed its position in the filtered range - to no longer in the range. Since we're lazily filtering the range, this means that when we advanced `first` (which referred to the `2`), the next even element is actually `6`. This now breaks `pairwise` - which promised to give us two _different_ elements.

## Whose fault is it?

The problem here is that we have a multipass algorithm (`pairwise`) that we mutated during (`++j`) in such a way that changed the elements in the filter view.

It's important to point out that once you have lazy filtering, mutability, and multipass - you can run into this situation. It doesn't actually even matter what the iterator model is [^rust].

[^rust]: Rust protects you here in the usual way - trying to construct an example that runs into a problem here involves having either two mutable borrows or one mutable and one immutable one. There's probably some way to construct something that breaks, I'm just not creative enough.

But it's at least worth asking: is there a different design of `filter` that doesn't have this issue? Well, the problem happens because of (1) lazy, (2) multipass and (3) mutation. If we only made a single pass, then there's no inconsistency with iterators that could come up. And if we didn't mutate, well, then of course we'd have no problem. And if the whole operation were eager - say `r | views::filter(pred)` simply returned a `vector` (which wouldn't be much of a view...) - then there's pretty obviously no problem.

We could fix the laziness by making `filter` eager, but I don't think that's really much of an option. That really wouldn't be `views::filter`. Laziness is valuable.

We could fix the multi-pass allowance by simply making `filter` unconditionally an input range.

And we could fix the mutation allowance by... actually no we can't. Even if `filter` also performed `views::as_const`, that's insufficient. A range of `int&` would turn into a range of `int const&`, that's good. But a range of `int*` would stay a range of `int*` (we can't mutate the pointers, so it would become a constant range), and we can still mutate _through_ the pointer. So we'd need a stronger `views::as_const` that would also turn ranges of `T*` into ranges of `T const*`. That's... potentially feasible. But then you'd also need to turn a range of `span<T>` into a range of `span<T const>`. And a range of `struct S { int* p; };` into... well... something? There's not really a feasible way to prevent _any_ kind of mutation.

So that leaves making `filter` unconditionally input. Is that a good idea? Today, `filter` is up to a bidirectional range. And that's pretty useful - there are a lot of things you can do with a bidirectional range. Some of them (like mutating while iterating over `pairwise`) are bad, and lead to unexpected behavior, but a lot of them are quite good and it would be unfortunate if we missed out on that functionality.

But once you allow `filter` to be multi-pass, you have to say something about this problem. Which the standard does, in [\[range.filter.iterator\]/1](https://eel.is/c++draft/range.filter#iterator-1):

> Modification of the element a `filter_view​::​iterator` denotes is permitted, but results in undefined behavior if the resulting value does not satisfy the filter predicate.

This is a fairly strong and broad statement. I've been stressing in this post that this kind of mutation (that changes an element from satisfying to not satisfying the predicate [^preserving]) is really only problematic in the multi-pass case. This sentence, on the other hand, calls it always undefined behavior, regardless.

[^preserving]: Predicate-preserving mutations are totally fine. `i += 2`, for instance? No issues. Note also that other kinds of mutation, such as having a predicate like `[](int& i){ i += 1; return i % 2 == 0; }`, are also UB because they fail to meet the semantic requires of `std::predicate`: invoking the function with the same input has to give the same output. But situations like that just obviously broken in a way that the other situations I'm talking about here are not.

The reason for this isn't so much that the standard library hates you, but more that it is actually exceedingly difficult to come up with a way to accurately describe what the specific situation is that leads to undefined behavior. So the standard library takes a broader outlook. Suggestions are always welcome.

## The Original Example

Nico's example did this:

```cpp
// increment even elements:
for (int& i : coll | std::views::filter(isEven)) {
    ++i; // UB: but works
}
```

This is, per the wording of the standard library, undefined behavior.

But this example is... fine. We're doing a single pass through the elements, so even though we're doing the bad kind of mutation (changing our elements from satisfying the predicate to not), there's no place for our algorithm (the `for` loop) to get into a wacky state.

It's only when you add multi-pass into the mix that things can go wrong, and it's in these situations that such mutation should definitely be avoided:

```cpp
auto evens = coll | std::views::filter(isEven);

// first pass
for (int& i : evens) {
    ++i;
}

// second pass
for (int& i : evens) {
    ++i;
}
```

This isn't a multi-pass algorithm like `pairwise` and `min_element` were, but I am literally iterating over the loop twice. This is exactly the kind of thing you should avoid - and, indeed, this example is broken (the second loop does actually do something).

So, in short: with `filter` (but, notably, neither `take_while` nor `drop_while`), you have to be careful about mutating elements in a way that causes them to no longer satisfy the predicate. This will cause unexpected behavior for multi-pass algorithms. But if you're just doing a single pass, then you can get away with it. It's fine?

Does this mean `filter` is broken? As I said, this behavior is inherent once you have lazy filtering, with a multi-pass algorithm, that does mutation. We can't fix this by making it eager or somehow preventing mutation, but we could fix it by prohibiting multi-pass. That's a big loss in functionality though, and I'm not sure the tradeoff is really worth it.

Importantly, one thing I haven't mentioned thus far is caching. That's because caching isn't really relevant to this problem. A `filter` that didn't cache would run into the same issues. Not with the two-loop example above, but still with the `pairwise` example from earlier.

It's a pretty interesting scenario to carefully consider, but I just don't think it's reasonable to call `views::filter` broken in this scenario. There's just no way to making a lazy, multi-pass, mutating filter do the "right" thing.

---
