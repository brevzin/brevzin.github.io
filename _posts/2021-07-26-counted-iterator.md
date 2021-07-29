---
layout: post
title: "Counting in Iteration Models"
category: c++
tags:
  - c++
  - c++20
  - ranges
---

There's a really interesting issue pointed out in the [July 2021 mailing](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/#mailing2021-07) by way of [P2406R0](https://wg21.link/p2406r0).

Basically, in C++, the iterator loop structure ordering is as follows (I wrote it with a goto to make the ordering more obvious. Note that in C++, we start with the `it != end` check, not the `++it` operation. The point of this ordering is to focus on the transition from one position to the next):

```cpp
loop:
    // advance
    ++it;
    // done?
    if (it != end) {
        // read
        use(*it);
        goto loop;
    }
```

In C++20, `counted_iterator` is an iterator adaptor that simply adds a starting count to the iterator, decrements it on each increment, and compares it as part of the iterator equality check. The count doesn't participate in dereference.

In terms of order of operations, using a `counted_iterator` in a loop would look like this:

```cpp
loop:
    // advance
    --count;
    ++it;
    // done?
    if (count != 0 && it != end) {
        // read
        use(*it);
        goto loop;
    }
```

We *always* increment the underlying iterator as we reduce the length, then we check if we reached the end (which could happen if either `count == 0` or `it == end`), and then we use the iterator. 

Notably, we increment the underlying iterator even if we decremented `count` to `0`. The issue pointed out in the paper is that this last increment could be very problematic (or, at least, undesirable). This isn't strictly a C++ problem. D's `take` behaves [exactly the same way](https://github.com/dlang/phobos/blob/master/std/range/package.d#L2256-L2263) (unsurprising, since D's range model is basically the same as C++'s iterator model).

But what we really want here is something like this:

```cpp
loop:
    --count;
    if (count != 0) {
        ++it; // guarded
        if (it != end) {
            use(*it);
            goto loop;
        }
    }
```

That is, ensure that we only increment in the underlying iterator when we have to.

In my [CppNow talk](https://t.co/DuwKG03ToN?amp=1) this year, I looked at the iteration models of several different languages. I grouped C++, D, and C# together as "reading" languages - based on them having an idempotent function that "reads" the current element. Those models behave similarly in a lot of circumstances, and I showed some benefits of that (certain algorithms that you can do in those languages that you can't without that operation) and some downsides (such as the filter-map issue inherent to this model). But I kind of treated the three as broadly equivalent. 

But they're not in this case.

While C++ and D have `advance`, `done?`, and `read` as three distinct operations, that's not the case in C#. In C#'s `IEnumerator`, `advance` and `done?` are a single operation named `MoveNext`. In that model, you'd implement `take` as follows:

```cpp
template <IEnumerator E>
struct TakeEnumerator {
    E underlying;
    int count;
    
    auto MoveNext() -> bool {
        if (count > 0) {
            --count;
            return underlying.MoveNext(); // guarded
        } else {
            return false;
        }
    }
    
    auto Current() -> decltype(auto) {
        return underlying.Current();
    }
};
```

I hadn't really previously considered the situations in which the C# model could do better than the C++/D one. I had only considered the C++/D/C# model as a whole against the Python/Rust/etc model.

Of course, the Rust model does not have this problem either:

```cpp
template <Iterator I>
struct TakeIterator {
    I underlying;
    int count;
    
    auto next() -> Optional<I::reference> {
        if (count > 0) {
            --count;
            return underlying.next(); // guarded
        } else {
            return nullopt;
        }
    }
};
```

The shape of this solution is nearly the same as the C# one. In both cases, we guard access to the underlying enumerator/iterator/range/cat/whatever on the `count` check. 

I thought this was just an interesting example where grouping `advance` and `done?` together in a single operation addresses a problem that exists largely because the two operations are separate. In a way this is similar to the filter-map problem that exists because `advance` and `read` are separate. 

While there are also clear advantages of `advance` and `read` being separate operations (being able to `advance` cheaply to skip ahead or jump backwards), I haven't yet really thought about what the advantages of `advance` and `done?` being separate are. At the very least, the C++ iterator/sentinel model maps a little awkwardly onto the C# model simply because in C# you have to `MoveNext` to get to the first element, and in C++ that means extra state:

```cpp
template <input_iterator I, sentinel_for<I> S>
struct CppEnumerator {
    I first;
    S last;
    bool increment = false;
    
    auto MoveNext() -> bool {
        // don't increment the first time, but do
        // increment every other time
        if (increment) {
            ++first;
        }
    
        if (first != last) {
            increment = true;
            return true;
        } else {
            return false;
        }
    }
    
    auto Current() -> iter_reference_t<I> {
        return *first;
    }
};
```

And that extra checking *for all ranges* is probably worse than the extra checking that [P2406R0](https://wg21.link/p2406r0) suggests simply for `counting_iterator` (the paper doesn't do it precisely this way, this is my alteration of it):

```cpp
template <input_iterator I>
class counted_iterator {
    I current;
    iter_difference_t<I> length;
    
public:
    auto operator++() -> counted_iterator& {
        // existing implementation
        // ++current;
        // --length;
        
        // proposed implementation
        --length;
        if (random_access_iterator<I> or length != 0) {
            ++current;
        }
        return *this;
    }
};
```

The `random_access_iterator` check there exists, I'm guessing, because for random access iterators, incrementing has to be constant time and so we wouldn't expect that extra last increment to either be arbitrarily expensive (as it could be if we're `counting` after a `filter`) or leave the underlying in a bad state (as it could be if `I` is input-only). And so, in that case, perhaps it might be better to avoid that extra `length != 0` check?

But we'd do a `length != 0` check anyway when we compare this iterator to its corresponding sentinel so I'm not sure there is actually extra cost there. The `random_access_iterator` check might just be adding complexity. 

In any case, I thought this was a really interesting issue, both in of itself and also in that it exposes a functional difference between the C++ and D iteration models and the C# one. 