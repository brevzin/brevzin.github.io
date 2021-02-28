---
layout: post
title: "C++20 Range Adaptors and Range Factories"
category: c++
tags:
  - c++
  - c++20
  - ranges
---

Ranges in C++20 introduces with it a bunch of range adaptors (basically, algorithms that take one or more ranges and return a new "adapted" range) and range factories (algorithms that return a range but without a range as input). All of these algorithms have several important properties, and I've found that it's a bit difficult to actually determine what those properties are just by looking at the standard, so I'm hoping to make this post serve as that reference.

The properties I'm talking about:

* The range's **reference** type. This is the type that you directly interact with, it's what the iterator's `operator*` gives you. This could be a language reference type (the reference type of `vector<int>` is `int&`) but it does not have to be. Nothing in this post will refer to the range's value type.
* The range's **traversal category**. There are five traversal categories: input, forward, bidirectional, random access, and contiguous. An adapted range's traversal category may differ from the input range's traversal category, and it's important to understand how. Typically, a range adaptor will have a ceiling for the category that it can pass through - in this case I will use the phrase "at most X" to indicate that the resulting traversal category is the weaker category between the input range's category and X.
* Under what conditions is the range a **common range**? A range is a common range if `begin(r)` and `end(r)` return the same type. In other words, that a range's iterator type and sentinel type have the same type. The C++17 standard library only supports common ranges, C++20 starts supporting having a distinct sentinel type. To this end, many range adaptors try hard to be common ranges in order to ensure maximum comaptibility with preexisting algorithms. 
* Under what conditions is the range a **sized range**? Can it provide an `O(1)` member `size()`?
* Under what conditions is the range **const-iterable**? If I have a `const` object of the adapted range type, is it actually still a range that I can iterate over? This is not the case for all C++20 ranges. 
* Under what conditions is the range a **borrowed range**? This means that if you have an iterator into the range, and the range is destroyed, the iterator still does not dangle.

There are a few conventions I use in this post in order to be a bit terse hopefully without losing meaning, which are basically a rough mix of Rust and Haskell syntax:

* lower case letters refer to values, upper case letters refer to types. `w` is an object of type `W`.
* `[T]` denotes a range whose **reference** type is `T`. So `vector<int>` could be denoted as `[int&]` while `vector<int> const` could be `[int const&]`. `[[U]]` denotes a range whose reference is a range whose reference is `U` (i.e. a range of range of `U`).
* `A -> B` denotes a callable that when called with an object of type `A` produces an object of type `B`. For instance, `A -> bool` is a unary predicate that takes `A`. `(A, A) -> bool` is a binary predicate that takes two `A`s. 

For help understanding what certain range adaptors and factories do, I find that it's helpful to simply print what they are. Until [P2286](https://wg21.link/p2286) gets adopted, the way to do this is to use `fmt` which allwos for formatting ranges. For [example](https://godbolt.org/z/oe75W1):

```cpp
#include <ranges>
#include <fmt/format.h>
#include <fmt/ranges.h>

int main() {
    using namespace std;

    auto squares_under_200 =
        views::iota(0)
        | views::transform([](int i){ return i*i;})
        | views::take_while([](int i){ return i < 200; });

    // {0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 121, 144, 169, 196}
    fmt::print("squares under 200: {}\n", squares_under_200);
}
```

<hr />

### Contents

**Range Factories**
* [empty_view](#empty)
* [single](#single)
* [iota](#iota)
* [istream_view](#istream_view)

**Range Adaptors**
* [filter](#filter)
* [transform](#transform)
* [take](#take)
* [take_while](#take_while)
* [drop](#drop)
* [drop_while](#drop_while)
* [join](#join)
* [split](#split)
* [common](#common)
* [reverse](#reverse)
* [elements, keys, and values](#elements)

<hr />

### `empty_view<T>()` {#empty}

Produces an empty range. `T` must be an object type.
    
* reference: `T&`
* category: contiguous
* common: always
* sized: always (`== 0`)
* const-iterable: always
* borrowed: always
    
### `single(t: T)` {#single}

Produces a range consisting of the single value: `t`.

* reference: T&
* category: contiguous
* common: always
* sized: always `(== 1`)
* const-iterable: always
* borrowed: never
    
### `iota`

There are three overloads of `iota`:

```cpp    
iota(w: W) -> [W]
iota(w: W, b: B) -> [W]
iota(w: W, w2: W) -> [W]
```

Produces a range starting with `w` and incrementing it either forever (in the `iota(w)` case) or until the value matches the bound (in the other cases).

```
>>> iota(0)
[0, 1, 2, ... ] # an infinite range
>>> iota(0, 5)
[0, 1, 2, 3, 4]
```

* reference: `W` (not `W&`!)
* category:
    * if `W` is [advanceable](http://eel.is/c++draft/ranges#concept:advanceable), then random access
    * otherwise, if `W` is [decrementable](http://eel.is/c++draft/ranges#concept:decrementable), then bidirectional
    * otherwise, if `W` is [incrementable](http://eel.is/c++draft/iterator.concept.inc#concept:incrementable), then forward
    * otherwise, input
* common: in the case where the bound is the same type as the initial value
* sized: when the bound is provided and you can subtract the bound from the initial value
* const-iterable: always
* borrowed: always (the iterator owns the `W`)
    
### `istream_view<T>(s)` {#istream_view}

Produces a range of `T` by reading (using `operator>>`) from the provided stream (`s`). `T` must be an object type.
    
* reference: `T&`
* category: input
* common: never (the iterators are non-copyable so there's no benefit to providing an interface that matches C++17 legacy)
* sized: never
* const-iterable: no
* borrowed: never

### `filter(r: [T], f: T -> bool) -> [T]` {#filter}

Produces a range of the elements of `r` that satisfy the unary predicate `f`
    
```
>>> filter([1, 2, 3, 4], e => e % 2 == 0)
[2, 4]
```
    
* reference: `T` (same as input range)
* category: at most bidirectional
* common: when `r` is common
* sized: never
* const-iterable: no
* borrowed: never
    
### `transform(r: [T], f: T -> U) -> [U]` {#transform}

Produces the range `[f(e) | e <- r]`. Many languages call this `map`.
    
```
>>> transform(["a", "quick", "brown", "fox"], e => e[0])
['a', 'q', 'b', 'f']
```
    
* reference: `U`
* category: at most random access
* common: when `r` is common
* sized: when `r` is sized, in which case the same size as `r`
* const-iterable: when `r` is const-iterable and `f` is const-invocable
* borrowed: never
    
### `take(r: [T], n: N) -> [T]` {#take}

Produces a range that includes the first `n` elements of `r`, or the entirety of `r` if `r` does not have `n` elements.
   
```   
>>> take([1, 2, 3, 4], 2)
[1, 2]
>>> take([1, 2, 3, 4], 8)
[1, 2, 3, 4]
```
    
* reference: `T` (same as input range)
* category: same as `r` (even preserves contiguous)
* common: when `r` is sized and random access
* sized: when `r` is sized, in which case the min of `n` and `ranges::size(r)`
* const-iterable: when `r` is const-iterable
* borrowed: when `r` is borrowed

### `take_while(r: [T], f: T -> bool) -> [T]` {#take_while}

Produces a range that includes all the elements of `r` that satisfy `f` until `f` evalutes to `false`.

```
>>> take_while([1, 2, 3, 1, 2, 3], e => e < 3)
[1, 2]
```

* reference: `T` (same as input range)
* category: same as `r` (even preserves contiguous)
* common: never (unlike `filter`, we don't know what end iterator to use)
* sized: never
* const-iterable: when `r` is const-iterable and `f` is const-invocable
* borrowed: never

### `drop(r: [T], n: N) -> [T]` {#drop}

Produces a range that excludes the first `n` elements of `r`, or is empty if `r` does not have `n` elements.

```
>>> drop([1, 2, 3, 4], 2)
[3, 4]
>>> drop([1, 2, 3, 4], 8)
[]
```

* reference: `T` (same as input range)
* category: same as `r` (even preserves contiguous)
* common: when `r` is common
* sized: when `r` is sized, in which case the max of `0` and `ranges::size(r) - n`
* const-iterable: when `r` is const-iterable
* borrowed: when `r` is borrowed

### `drop_while(r: [T], f: T -> bool) -> [T]` {#drop_while}

Produces a range that excludes all the elements that satisfy `f` until the `f` evalutes to `false`.

```
>>> drop_while([1, 2, 3, 1, 2, 3], e => e < 3)
[3, 1, 2, 3]
```

* reference: `T` (same as input range)
* category: same as `r` (even preserves contiguous)
* common: when `r` is common
* sized: never
* const-iterable: never
* borrowed: when `r` is borrowed

### `join(r: [[T]]) -> [T]` {#join}

Produces a range that flattens a range of range of `T` into a range of `T`. Many languages call this `flatten`.

```
>>> join([[1, 2], [3], [4, 5, 6]])
[1, 2, 3, 4, 5, 6]
```

* reference: `T` (the inner range's reference)
* category:
    * if `r` a range of glvalue ranges, then at most bidirectional based on the inner range's traversal category.
    * otherwise, input
* common: when all of the following hold:
    * `r` is forward and common
    * `r` is a range of glvalue ranges
    * the inner range is forward and common
* sized: never
* const-iterable: when `r` is const-iterable
* borrowed: never

### `split` {#split}

There are two overloads of `split`:

```cpp
split([T], v: T) -> [[T]]
split([T], p: [T]) -> [[T]]
```

Produces a range that splits a range of `T` into a range of range of `T` on the delimiter.

```
>>> split("a quick brown fox", ' ')
["a", "quick", "brown", "fox"]
>>> split("a||b|c||d", "||")
["a", "b|c", "d"]
```

* reference: `[T]` (i.e. range of the underlying range's reference type)
* category: at most forward (see [P2210](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p2210r1.html)).
* common: when `r` is forward and common
* sized: never
* const-iterable: when `r` is const-iterable
* borrowed: never

### `common(r: [T]) -> [T]` {#common}

Produces the same elements in `r` but ensures that the resulting range is a common range. This exists as a shim to be able to use C++17 iterator-pair algorithms with C++20 iterator-sentinel algorithms.

* reference: `T` (same as input range)
* category:
    * if `r` is random access and sized, then same as the input range (preserves contiguous)
    * otherwise, at most forward
* common: always (this is the only point of this adaptor)
* sized: when `r` is sized, in which case the same size as `r`
* const-iterable: when `r` is const-iterable
* borrowed: when `r` is borrowed

### `reverse(r: [T]) -> [T]` {#reverse}

Produces a range that reverses the elements of `r`. Requires that `r` be at least bidirectional.

```
>>> reverse([1, 2, 3])
[3, 2, 1]
```

* reference: `[T]` (same as the input range)
* category: at most random access
* common: always
* sized: when `r` is sized, in which case the same size as `r`
* const-iterable: when `r` is const-iterable
* borrowed: when `r` is borrowed

### `elements` {#elements}

This range adaptor comes with a few specialized variants with custom names:

```cpp
elements<I>(r: [(T1, ..., TI, ..., TN)]) -> [TI]
keys(r: [(T1, T2, ..., TN)]) -> [T1]
values(r: [(T1, T2, ..., TN)]) -> [T2]
```

Produces a range of the `I`th (`elements<I>`) / 1st (`keys`) / 2nd (`values`) elements of a range of tuples. `keys` and `values` are most typically used when dealing with assocative containers. Requires that `r` is a range of tuples.

```
>>> r = [("Lovelace", 1815), ("Turing", 1912)]
>>> elements<1>(r)
[1815, 1912]
>>> keys(r)
["Lovelace", "Turing"]
>>> values(r)
[1815, 1912]
```

* reference: `tuple_element_t<I, T>` where `T` is the reference type of `r`. For `keys`, `I == 0`. For `values`, `I == 1`.
* category: at most random access
* common: when `r` is common
* sized: when `r` is sized, in which case the same size as `r`
* const-iterable: when `r` is const-iterable
* borrowed: when `r` is borrowed (this is a special case of `transform` where the transform is encoded into the type)