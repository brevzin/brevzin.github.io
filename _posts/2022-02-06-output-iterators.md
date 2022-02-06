---
layout: post
title: "Improving Output Iterators"
category: c++
tags:
  - c++
  - d
  - ranges
---

Let's say we had a range, represented by a pair of pointers, that we wanted to copy into another pointer. We might write that like so:

```cpp
template <typename T, typename U>
void copy(T* first, T* last, U* out) {
    for (; first != last; ++first) {
        *out++ = *first;
    }
}
```

For trivially copyable types, this could be improved to `memcpy`, and maybe you might want to partially unroll this loop since we know how many iterations we have to do -- but let's ignore those kinds of details.

We can generalize this to an arbitrary input range and an arbitrary output iterator by simply changing the types:


```cpp
template <typename InputIt, typename OutputIt>
void copy(InputIt first, InputIt last, OutputIt out) {
    for (; first != last; ++first) {
        *out++ = *first;
    }
}
```

This is where the C++ iterator model came from: by generalizing from pointers. Consequently, we end up with the same syntax. We say that `out` is an output iterator for `T` if you can do this:

```cpp
*out++ = t;
```

The advantage of this approach is that this operation just works if you have a forward iterator with a suitably mutable reference type. `int*`, `list<int>::iterator`, etc, are all output iterators. And that is quite a big advantage.

The disadvantage of this approach is what happens when you want to write an output iterator that is not actually an input iterator - one specifically dedicated to being an output iterator. How do you implement such a thing? For input iterators, you already have to write an `operator*` and an `operator++` (and the underlying type probably already has an `operator=`), but in the output case we don't actually have three different operations that we're trying to implement. It's more like we're trying to implement an `operator*++=`. Which, of course, is not a thing.

For an example of what I mean, let's take a look at `std::back_insert_iterator`. This is probably the output-only iterator that people are most familiar with. For example:

```cpp
int arr[] = {1, 2, 3, 4, 5};
vector<int> vec;
copy(begin(arr), end(arr), back_inserter(vec));
```

The goal here is to put all the elements in `arr` into the end of `vec`. We can't just use `vec.begin()` here - that would be _syntactically_ valid (`vector<int>::iterator` is a valid output iterator), but `vec` is empty so we can't just write five elements into nothing. We need to `vec.push_back(i)` for each element. And that's what `back_inserter` does for us: it constructs an output iterator that invokes `push_back`.

How do we do that?

Well, we need `*out++ = t;` to invoke `vec.push_back(t)`. But in order to do that, we need to provide an `operator*` that returns something whose assignment invokes `push_back`, and we need an `operator++` (both of them) that do... something. Incrementing doesn't make any sense in this context. Nor does dereference for that matter. So one approach would be:

```cpp
template <typename C>
class back_inserter {
    C* cont_;

public:
    back_inserter(C& c) : cont_(&c) { }

    // these do nothing
    auto operator*() -> back_inserter& { return *this; }
    auto operator++() -> back_inserter& { return *this; }
    auto operator++(int) -> back_inserter { return *this; }

    // this one does something
    auto operator=(typename C::value_type const& val)
        -> back_inserter&
    {
        cont_->push_back(val);
        return *this;
    }
};
```

This... works. We have an output iterator, it solves the problem.

But it's fairly awkward. There's boilerplate and then there's... writing three functions that do literally nothing just to satisfy an API. It feels wrong, like there's something missing.

Having an awkward API to implement is one thing, but ultimately the problem is actually quite a bit worse than that.

In the example above, I'm not trying to just "output" one element into the `std::vector`. I'm trying to output a whole range. In fact, this is the best case - I'm trying to output a range whose size I know. But the implementation using my `copy` algorithm (or `std::copy` or `std::ranges::copy` in real life) with `back_inserter(vec)` is going to `push_back` one element at a time. Each `push_back` is going to do a bounds check and potentially reallocate, and there could be multiple such reallocations.

But if we knew specifically that we wanted to append a range to the end of a `std::vector`, we should do it this way:

```cpp
vec.insert(vec.end(), begin(arr), end(arr));
```

This would do a single allocation (if necessary), and then do a bunch of copies which wouldn't need any bounds checks. That can make it [much faster](https://quick-bench.com/q/TTbsRVxjQLQMEbP0J5X3pp1IoxQ) (2.7x in that simple benchmark).

In C++23, with the imminent adoption of [P1206R7](https://wg21.link/p1206r7), the above is even more ergonomic (or, put differently, actually ergonomic):

```cpp
vec.append_range(arr);
```

The problem here isn't `back_inserter`. There's simply no way to write an output iterator to do this operation efficiently, since the API for output iterators can only get one element at a time.

### Towards a better Output Iterator API

Fundamentally, there are two operations that want to be able to do:

* output a single element
* output a range of elements

Technically the former is just a special case of the latter (a single element is just a range of one, and we even have `views::single` to make that easy), but I think it's still reasonable to think of them as separate.

To try to figure out how we might improve, let's take a look at D. D doesn't have the concept of iterator, its primitive is a range (you can see a brief overview of the model in my [CppNow 2021 talk](https://www.youtube.com/watch?v=d3qY4dZ2r4w&t=976s), although I didn't talk about output ranges). Since ranges are primitives in D, it's not surprising that D's output ranges actually handle ranges well.

In D, the [output range primitive](https://dlang.org/library/std/range/primitives/put.html) is called `put` and takes a range `R` and an object `E`:

```d
void put(R, E) (
  ref R r,
  E e
);
```

`put(r, e)` is defined as the first of many potential candidate expressions that are valid (I'm skipping a few details here that aren't particularly relevant), which makes it very customizable:

1. `r.put(e)`
2. `r.front = e; r.popFront()` -- this is the D equivalent to C++'s `*out++ = e;`
3. `r(e)`
4. `r.put([e])`
5. `r.front = [e]; r.popFront()`
6. `r([e])`
7. `for (; !e.empty; e.popFront()) put(r, e.front);` -- this is calling `put(r, elem)` for each `elem` in the range `e`

First, we try three different ways to put `e` into `r`. Then, we try three different ways to put `[e]` (a single-element range) into `r` (note that these are the same three). Lastly, if `e` is a range, we try to `put` each element of `e` into `r`.

Note that the last option in `put` is recursive. The interesting consequence of that is if you write an output range which accepts an `int`, you can `put` not just an `int` into it but also a range of `int` or a range of range of `int` or ...

Also, because `put(r, e)` tries to both put `e` directly and also by wrapping it into a range, you can be an output range of `int` either by accepting a single `int` or by accepting a range of `int`. [For example](https://godbolt.org/z/EjqnhWY3d):

```d
void main()
{
    import std.range.primitives;
    import std.stdio;

    // takes a single int
    static struct A
    {
        void put(int i)
        {
            writeln(i);
        }
    }

    // takes a range of int
    static struct B
    {
        void put(R)(R r)
            if (isInputRange!R && is(ElementType!R == int))
        {
            writeln(r);
        }
    }

    // both are output ranges of int
    static assert(isOutputRange!(A, int));
    static assert(isOutputRange!(B, int));

    auto a = A();
    put(a, 1);        // prints 1
    put(a, [2]);      // prints 2
    put(a, [[[3]]]);  // prints 3

    auto b = B();
    put(b, 1);        // prints [1]
    put(b, [2]);      // prints [2]
    put(b, [[3]]);    // prints [3]
}
```

There are a few very interesting to point out about the approach D takes.

A mutable input range in D can be used as an output range too (these are the 2nd and 5th options above). This is similar to the C++ model.

However, writing an output-only iterator in D is much more straightforward - you only need to write `void put(E);` rather than having to write `operator*`, `operator++`, and `operator=`. For instance, a `back_insert_iterator` build on the D model would just look like:

```cpp
template <class C>
class put_back_inserter {
    C* cont_;
public:
    put_back_inserter(C& c) : cont_(&c) { }

    void put(typename C::value_type const& val) {
        cont_->push_back(val);
    }
};
```

That's quite a bit nicer.

Moreover, we can also resolve the performance issue I mentioned earlier by adding a second overload of `put` that accepts appropriate ranges:

```cpp
template <class C>
class put_back_inserter {
    C* cont_;
public:
    put_back_inserter(C& c) : cont_(&c) { }

    void put(typename C::value_type const& val) {
        cont_->push_back(val);
    }

    template <ranges::input_range R>
      requires std::convertible_to<ranges::range_reference_t<R>, typename C::value_type>
    void put(R&& r) {
        // eventually, this would be
        // cont_->append_range(r);

        // but for now, it's an insert() call
        // this isn't quite right because r needs to be common, but
        // good enough for this blog post's purposes
        cont_->insert(cont_->end(), ranges::begin(r), ranges::end(r));
    }
};
```

Again, quite nice.

And, on top of that, there's one more positive aspect worth mentioning here: functions are output iterators too. It's been brought up often that a sink should be usable as an output iterator. It's already possible to implement a C++ output iterator that invokes a function when an element is pushed (and this is even easier in D), but this model side-steps that extra wrapping by just letting you just use a function directly.

Also, quite nice.

The downside of the D approach here, especially where C++ is concerned, is the Do-What-I-Mean aspect of it. `put(r, e)` can both put a single-element or a range. The problem example brought up with algorithms like this is `std::any`, not because lots and lots of code uses `std::any` specifically but because its permissive conversions are representative of all manner of implicit conversions (and keep in mind as I'm writing this there is a big discussion on whether or not `vector<char>` should be convertible to `std::string_view` -- see [P2499R0](https://wg21.link/p2499) and [P2516](https://wg21.link/p2516)).

For a concrete example, let's say you wrote something like:

```cpp
// v holds 3 any's, each of which hold an int
std::vector<std::any> v = {1, 2, 3};

// what should this do?
put(out, v);
```

Even if `out` is an output range for `std::any`, this could still do one of two different things:

* if `out` provides a `void put(std::any)`, then `put(out, v)` would put one `std::any` (that is itself a `std::vector<std::any>`) into `out`
* if `out` provides a `put` that accepts a range of `std::any` (using the same kind of constrained template I showed earlier), then `put(out, v)` would put three `std::any` objects (that each hold an `int`) into `out`.

And if `out` provides both? Then the latter approach wins, although you really have to work through the implementation details:

```cpp
struct Out1 {
    void put(std::any);

    template <ranges::input_range R> requires /* ... */
    void put(R&&)
};

struct Out2 {
    template <std::convertible_to<std::any> T>
    void put(T&&);

    template <ranges::input_range R> requires /* ... */
    void put(R&&)
};
```

With `Out1`, `out.put(v)` would prefer the range overload because it doesn't require a conversion, so we end up putting three `std::any` objects into `out`.

With `Out2`, the call `out.put(v)` is ambiguous. As is the call to `out.put([v])` (or the C++ equivalent of that). So we fall back to treating `v` as a range and iterating through it, which recurses to `out.put(v[0])`. Now we no longer have a range, so only the value overload is viable, so we end up putting three `std::any` objects into `out` as well.

That's pretty subtle and more than a bit concerning from a code understandability perspective, I think, which is probably why even though D potentially supports efficient range-based outputting, its own `copy` algorithm _does not do this_. Instead, its [default case](https://github.com/dlang/phobos/blob/v2.098.1/std/algorithm/mutation.d#L422-L423) is a loop:

```d
foreach (element; source)
    put(target, element);
```

Avoiding this potential range-or-value ambiguity is why (in [P1206](https://wg21.link/p1206)) we're adding a new `insert_range(pos, r)` to the containers rather than adding a new overload `insert(pos, r)` that takes a range.

All in all, several arguably large upsides and one arguably large downside.

### Towards a better Output Iterator API... in C++

Let's start by simply implementing the D model in C++ to get a feel for what it does. This approach -- picking the first valid option of several possible ones -- lends itself very nicely to a [declarative]({% post_url 2019-09-23-declarative-cpos %}) approach.

When I said earlier that D picks the first of seven valid expressions (skipping a few options for simplicity), that wasn't quite right. D actually groups the two similar sets of three under the name `doPut`. We can start by doing the same (I'm using [Boost.HOF](https://www.boost.org/doc/libs/master/libs/hof/doc/html/doc/src/adaptors.html) function adaptors in the implementation here):

```cpp
namespace hof = boost::hof;
namespace ranges = std::ranges;

#define FWD(x) static_cast<decltype(x)&&>(x)
#define RETURNS(expr) -> decltype(expr) { return expr; }

inline constexpr auto do_put = hof::first_of(
    [](auto&& out, auto&& e) RETURNS(void(out.put(FWD(e)))),
    [](auto&& out, auto&& e) RETURNS(void(*out++ = FWD(e))),
    [](auto&& out, auto&& e) RETURNS(void(std::invoke(out, FWD(e))))
);
```

This covers the first three options (if we just pass `e`) and also the next three options (if we pass `[e]`). The last case is tricky because we need to be recursive, which requires using `hof::fix`:

```cpp
inline constexpr auto put = hof::fix(hof::first_of(
    [](auto&&, auto&& out, auto&& e)
        RETURNS(do_put(out, FWD(e))),
    [](auto&&, auto&& out, auto&& e)
        RETURNS(do_put(out, ranges::subrange(&e, &e+1))),
    []<ranges::range E>(auto&& put, auto&& out, E&& e)
        requires requires (ranges::iterator_t<E> it) {
            put(out, *it);
        }
    {
        auto first = ranges::begin(e);
        auto last = ranges::end(e);
        for (; first != last; ++first) {
            put(out, *first);
        }
    }
));
```

And that completes the implementation.

The way I'm doing `[e]` is `subrange(&e, &e+1)`. That's kind of like `views::single(e)`, except avoiding copying `e`. Ideally, we also preserve its value category (as is, this is always a range consisting of one lvalue), but I didn't want to muddy this post with those details.

I like this approach more than the typical approach of just writing a function object type with a single properly-constrained `operator()`, which might seem like it'd be a better idea here especially due to recursion... simply because with so many options the constraint that you have to provide is obnoxious. For completeness though, an alternative implementation for `put` (still based on `do_put`) is:

```cpp
struct put_fn {
    template <class R, class E>
        requires invocable<decltype(do_put), R, E>
              or invocable<decltype(do_put), R, ranges::subrange<E*>>
              or ranges::range<E and invocable<put_fn, R, ranges::range_reference_t<E>>
    constexpr auto operator()(R&& out, E&& e) const {
        if constexpr (invocable<decltype(do_put), R, E>) {
            return do_put(FWD(out), FWD(e));
        } else if constexpr (invocable<decltype(do_put), R, ranges::subrange<E*>>) {
            return do_put(FWD(out), ranges::subrange(&e, &e + 1));
        } else {
            auto first = ranges::begin(e);
            auto last = ranges::end(e);
            for (; first != last; ++first) {
                (*this)(out, *first);
            }
        }
    }
};
inline constexpr put_fn put;
```

See what I mean? It's better, in the sense that it's quite clear that this is a binary callable, which is far less obvious when you're grouping multiple lambdas together -- especially when you have to use a fixed-point combinator to achieve recursion and thus all your lambdas look like they're ternary.

But, oof... that constraint...

You can see both implementations [here](https://godbolt.org/z/1zdrPrjTT), with a new version of `back_inserter` that uses the new model.

### Towards a better Output Iterator API in C++, take 2

The above helps set the stage for what might be possible, but it certainly wouldn't work for C++ as-is due to the issue I brought up earlier. We don't want the same name to do both single-element and range-based outputting, that's just way too much do-what-I-mean for a language with so many implicit conversions.

But that's fairly easily addressable by simply providing the two different pieces of functionality under two different names.

For instance, we could have a `ranges::put(out, e)` which picks the first valid expression out of:

1. `out.put(e);`
2. `*out++ = e;`
3. `out(e);`

And then we could have a `ranges::put_range(out, r)` which picks the first valid expression out of:

1. `out.put_range(r);`
2. `ranges::for_each(r, bind_front(ranges::put, out));`

I'm deliberately omitting the option where, in D, `put(out, e)` can try to do something like `out.put([e])`. I don't think that adds much value, and this provides a pretty good layering.

Both customization point objects would still work with C++20 output iterators with the same semantics they have today, which is important.

This approach, I think, has clear value:

* it's much easier and more straightforward to implement an output iterator that isn't an input iterator: you provide a `put` (or also a `put_range`).
* output iterators become more flexible, since you can also provide a sink
* outputting a whole range can potentially be more efficient, since you're giving the function more information

It's worth noting that while we have nothing like `ranges::put` today, we do already have an algorithm like `ranges::put_range`: it's called `copy`. That's a fairly commonly used algorithm, and allowing it to be customized like this could lead to better performance.

Sure seems like it'd be worthwhile to me.

### Formatting and Quality of Implementation

Now that I've written all of that, it's probably about time I bring up the motivation for this post: formatting.

In the [{fmt} library](https://github.com/fmtlib/fmt) and `std::format`, formatting is based on using output iterators. You get a context object and `context.out()` is some output iterator you can use to format your type. A lot of the time, you can just `format_to()` and won't do any direct outputting yourself... but when you do use the output iterator, you'll likely alternate needing to put `char`s and `std::string_view`s.

The former is fine, but the latter brings up a problem. How do you write a `std::string_view` into an output iterator? This is the same issue we saw with `back_inserter` earlier. Your only options are:

```cpp
out = std::copy(sv.begin(), sv.end(), out);
out = std::ranges::copy(sv, out).out;
```

But that can be inefficient. Which is why this isn't actually what `{fmt}` does in its own implementation.

Instead, it has a algorithm called `copy_str`. Its [default implementation](https://github.com/fmtlib/fmt/blob/35c0286cd8f1365bffbc417021e8cd23112f6c8f/include/fmt/core.h#L729-L734) is pretty familiar:

```cpp
template <typename Char, typename InputIt, typename OutputIt>
FMT_CONSTEXPR auto copy_str(InputIt begin, InputIt end, OutputIt out)
    -> OutputIt {
  while (begin != end) *out++ = static_cast<Char>(*begin++);
  return out;
}
```

But there's this other [important overload too](https://github.com/fmtlib/fmt/blob/35c0286cd8f1365bffbc417021e8cd23112f6c8f/include/fmt/core.h#L1605-L1609):

```cpp
template <typename Char, typename InputIt>
auto copy_str(InputIt begin, InputIt end, appender out) -> appender {
  get_container(out).append(begin, end);
  return out;
}
```

For most of the operations in `{fmt}`, the implementation-defined type-erased iterator is `appender`, so this would be the overload used. And `appender` is a `back_insert_iterator` into a `buffer<char>`, which is a growable buffer (not unlike `vector<char>`) which has a [dedicated `append`](https://github.com/fmtlib/fmt/blob/35c0286cd8f1365bffbc417021e8cd23112f6c8f/include/fmt/format.h#L632-L644) for this case:

```cpp
template <typename T>
template <typename U>
void buffer<T>::append(const U* begin, const U* end) {
  while (begin != end) {
    auto count = to_unsigned(end - begin);
    try_reserve(size_ + count);
    auto free_cap = capacity_ - size_;
    if (free_cap < count) count = free_cap;
    std::uninitialized_copy_n(begin, count, make_checked(ptr_ + size_, count));
    size_ += count;
    begin += count;
  }
}
```

So here, we know that `std::copy` would be inefficient, so the library provides (and internally uses) a way to special case that algorithm for its particular output iterator.

Users could, technically, use this same algorithm for their own specializations of `formatter<T>`, although I should note that this algorithm is `fmt::detail::copy_str<char>`, which doesn't really suggest that it's particularly user-facing.

This begs the question of what the implementations of `std::format` will do. Will they just use `std::copy`? Implementations _could_ special case their own iterators, that falls under the umbrella Quality of Implementation (QoI) issues, since they know what their own iterator is.

But while implementations could special-case the specific iterator they choose for `std::format` (since there's really only two: one for `char` and one for `wchar_t`), they can't really even special case the general case of `std::back_inserter<std::vector<T>>` -- since users are allowed to specialize `std::vector<T>`.

And even relying on this kind of implementation strategy strikes me as a bit much. There are other use-cases for efficient range copy that aren't just in {fmt} or `std::format` (which is part of why Victor rejected [my pull request](https://github.com/fmtlib/fmt/pull/2740) to add a dedicated API for this to the format context - we don't need to have multiple different `copy` algorithms - one in general and one specifically for formatting), so something like the approach I'm outlining here seems worthwhile to pursue anyway.
