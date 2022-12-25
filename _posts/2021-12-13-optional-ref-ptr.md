---
layout: post
title: "<code class=\"language-cpp\">T*</code> makes for a poor <code class=\"language-cpp\">optional&lt;T&></code>"
category: c++
tags:
 - c++
 - c++20
 - optional
---

Whenever the idea of an optional reference comes up, inevitably somebody will bring up the point that we don't need to support `optional<T&>` because we already have in the language a perfectly good optional reference: `T*`.

And these two types are superficially quite similar, which makes the argument facially reasonable. Indeed, `optional<T&>` would certainly be implemented to have this shape:

```cpp
template <> struct optional<T&> {
    T* storage = nullptr;

    explicit constexpr operator bool() const { return storage; }
    constexpr auto operator*() const -> T& { return *storage; }
    constexpr auto operator->() const -> T* { return storage; }
};
```

Not only do `T*` and `optional<T&>` have the same representation, but they even have the same meaning for their contextual conversion to `bool`, their dereference operator, and their arrow operator.

The purpose of this post is to point out that, despite these similarities, `T*` is simply not a solution for `optional<T&>`. There are several reasons for this, but I'll start with what is overwhelmingly the strongest.

### `optional<U>` just works, even for `U=T&`

Let's say you want to write an algorithm that given any range returns the first element in it (the point here isn't specific to Ranges, but Ranges does make for good, familiar examples). If we have a precondition that the range is not empty, we could write that algorithm this way:

```cpp
template <ranges::range R>
constexpr auto front(R&& r) -> ranges::range_reference_t<R> {
    return *ranges::begin(r);
}
```

Now, despite the name, the `reference` type of a `range` need not actually be a language reference. If I passed in a `vector<int>`, I'd get back an `int&` that refers to the first element. But if I passed in something like `views::iota(0, 10)`, I'd get back an `int` (not a reference) with value `0`.

Let's say instead of having a precondition that the range is non-empty, I want to handle that case too. I want to write a _total function_ instead of a _partial function_. The best way to do that is either return _some_ value (if I can) or _no_ value (if I can't). That's an optional, that's what it's for: to handle returning something or nothing.

The way to spell that is:

```cpp
template <ranges::range R>
constexpr auto try_front(R&& r)
    -> optional<ranges::range_reference_t<R>>
{
    auto first = ranges::begin(r);
    auto last  = ranges::end(r);
    if (first != last) {
        return *first;
    } else {
        return nullopt;
    }
}
```

This would return an `optional<int>` for the `views::iota` case, which is fine. But it would try to return an `optional<int&>` for the `vector<int>` case, because the reference type is `int&` there. This doesn't work with `std::optional`.

Now, the argument goes that we don't _need_ `optional<int&>` to exist because we have `int*`. So let's try to metaprogram our way out of this box:

```cpp
template <typename T>
using workaround = conditional_t<
    is_reference_v<T>,
    add_pointer_t<T>, // add_pointer_t<int&> is int*
    optional<T>>;

template <ranges::range R>
constexpr auto try_front(R&& r)
    -> workaround<ranges::range_reference_t<R>>
{
    auto first = ranges::begin(r);
    auto last  = ranges::end(r);
    if (first != last) {
        return *first;
    } else {
        return {};
    }
}
```

Does this work? No, it doesn't.

First of all there's the issue that it's possible that even spelling `optional<int&>` is ill-formed (which I think it is allowed for the implementation to do). So the actual implementation of `workaround<T>` would need to be more complex, but let's just ignore that part.

The reason that this doesn't work is that `int*` actually has many significantly different semantics from `optional<int&>`, and one of those importantly different semantics is: construction. An `optional<int&>` would be constructible from an lvalue of type `int`, but an `int*` is not -- pointers require explicit construction syntax, while references have implicit construction syntax.

In order to return an `int*` for the `vector<int>` case, I can't do `*begin(v)`, I have to do `&*begin(v)`. But I can't do that for the `views::iota` cause, because there dereferencing the iterator gives me a prvalue. There I _do_ have to do `*begin(v)`.

Which means the real implementation would have to look more like:

```cpp
template <typename T>
using workaround = mp_eval_if_c<
    is_reference_v<T>,
    add_pointer_t<T>,
    optional, T>;

template <ranges::range R>
constexpr auto try_front(R&& r)
    -> workaround<ranges::range_reference_t<R>>
{
    auto first = ranges::begin(r);
    auto last  = ranges::end(r);
    if (first != last) {
        if constexpr (std::is_reference_v<ranges::reference_t<R>>) {
            return &*first;
        } else {
            return *first;
        }
    } else {
        return {};
    }
}
```

This is already, I think, really quite bad.

Now let's try to use it! If I want to grab the first element in a range _or_ provide a default value to handle the empty case (which is a very common thing to want to do, think about how many times you've probably done this in the case of map lookup where you have `it == m.end() ? something : it->second`), I might try to write:

```cpp
int value = try_front(r).value_or(-1);
```

And that works. For the `views::iota` case anyway, since `try_front(views::iota(~))` will give me an `optional`.

But passing in a `vector<int>` here won't compile, because we made that case return an `int*` instead of an `optional` and there is no `value_or` member on a pointer (or, indeed, any other kind of member either). We'd need to provide another workaround here.

Which... we can. It's not that hard to write a non-member `value_or` that works for both `optional<T>` and `T*`:

```cpp
template <typename P, typename U>
constexpr auto value_or(P&& ptrish, U&& dflt) {
    return ptrish ? *FWD(ptrish) : FWD(dflt);
}
```

And now we can instead write:

```cpp
int value = N::value_or(try_front(r), -1);
```

So far, we've made ourselves have a worse implementation of `try_front()` in order to return `T*`, which in turn led to a worse implementation of the usage of `try_front` to handle the `T*` case. At this point you might bring up something like the pipeline operator (`|>`, which would allow `try_front(r) |> N::value_or(-1)`, which at least has the same shape of the desired expression) or [unified function call syntax]({% post_url 2019-04-13-ufcs-history %}) (which, if you pick the right version, at least lets you write `try_front(r).N::value_or(-1)`, assuming a qualified call is supported there). But we still have the issue where we have to write our own `value_or()` which has to handle both `optional<T>` and `T*`.

Let's look at a different example. In my [CppNow 2021 talk](https://www.youtube.com/watch?v=d3qY4dZ2r4w) and again in my recent CPPP 2021 talk (video pending), I demonstrate what the Rust iterator model looks like if were to implement it in C++. In Rust, an `Iterator` is:

```rust
trait Iterator {
    type Item;
    fn next(&mut self) -> Option<Self::Item>;
}
```

which in C++20 concepts would translate into something like:

```cpp
template <typename I>
concept rust_iterator = requires (I i) {
    // for some reason in my talks, I stuck with the C++
    // naming of 'reference' here rather than instead
    // using the much better name 'item_type'
    typename I::item_type;
    { i.next() } -> same_as<optional<typename I::item_type>>;
};
```


And one of the examples that I show is how to implement a `map` iterator (what in C++20 we call `views::transform`), which looks like this:

```cpp
template <rust_iterator I, regular_invocable<typename I::item_type> F>
struct map_iterator {
    I base;
    F func;

    using item_type = invoke_result_t<F&, typename I::item_type>;

    auto next() -> optional<item_type> {
        return base.next().map(func);
    }
};
```

You can see this in action in Tristan Brindle's [flow library](https://github.com/tcbrindle/libflow/blob/ac56cc60a482ca309dc2c48d2ce13c093bfd74ea/include/flow/op/map.hpp#L34-L41) (the only difference there, outside of the names of things, is that his library has distinct treatment for infinite ranges). This, to me, is a really nice implementation that has a nice sort of symmetry: `map` for iterators is implemented in terms of `map` for `optional`.

Except of course, we don't have `optional<T&>` - which is _really_ important to have in this model. It's not just important to avoid copying objects that you just want to iterate over, but semantically it could be critical that you refer to _that_ `T` rather than simply _some_ `T`. So we know already that we have to change our uses of `optional<U>` (both in the `concept` and in the implementation of `map_iterator`) to use `workaround<U>` instead. But just like `T*` didn't have a `value_or` member function, it also does not like a `map` member function.

And so, _again_, we could write a workaround for that (where we _again_ have to be careful about the different kinds of construction that we have to do):

```cpp
template <typename P, typename F>
constexpr auto map(P&& ptrish, F f)
{
    using U = decltype(invoke(f, *FWD(ptrish)));
    using Ret = workaround<U>;

    if (ptrish) {
        if constexpr (is_reference_v<U>) {
            return &invoke(f, *FWD(ptrish));
        } else {
            return Ret(invoke(f, *FWD(ptrish)));
        }
    } else {
        return Ret();
    }
}

template <rust_iterator I, regular_invocable<I::item_type> F>
struct map_iterator {
    I base;
    F func;

    using item_type = invoke_result_t<F&, I::item_type>;

    auto next() -> workaround<item_type> {
        return map(base.next(), func);
    }
};
```

Which is also, to me, quite bad.

At this point I'd like to take a brief aside.

### `vector<bool>` is bad

You'll often hear that the design decision of specializing `vector<bool>` was a bad decision. Indeed, I've never met anybody that has argued that it was a good decision. The reason that this is so universally considered a bad decision is that it means that `vector<T>` behaves the same way for all `T`... _except_ `bool`. Which makes this container (the most-used one by far) a little jarring.

Now, `vector<bool>` and `vector<T>` are not even _that_ different. They have most of the same member functions (`vector<bool>` does not have `data()`, for instance), which mostly even do the same things - there are just a few small edge cases where you some things just don't work.

For instance:

```cpp
template <typename T>
void f(vector<T>& v) {
    for (auto& elem : v) {
        // use elem
    }
}
```

That works for all `T` _except_ `bool`, because `range_reference_t<vector<T>>` is `T&` for all `T` (and thus you can take an lvalue reference to it) _except_ when `T` is `bool`, where it's `vector<bool>::reference`, which is a proxy reference type. Since it's a prvalue, you can't bind a non-const lvalue reference to it. `auto const&` would have worked. `auto&&` would have worked. `auto` would have worked (but have slightly different meaning). Just not `auto&`.

This is why people don't like `vector<bool>`. It's not really a `vector<T>` because it behaves differently. Indeed, just this past week at work, we had to work around a `vector<bool>`-specific issue!

But they are still very very similar. They have the same kind of constructors, they have the same member functions, most of whom even have the same semantics. There are many aspects of C++ for which there is wide disagreement in the community about what is good, but people are pretty uniform in the view that `vector<bool>` should _not_ have been a specialization (and that, seprately, a `dynamic_bitset` would have been useful - and probably much better at being a dynamic bitset than `vector<bool>` is anyway).

For more, see Howard Hinnant's [On vector&lt;bool>](https://isocpp.org/blog/2012/11/on-vectorbool).

### ... which makes `T*` an even worse `optional<T&>`

If we all agree that `vector<bool>` is bad because of several subtle differences with `vector<T>`, then surely we should all agree that `T*` is a bad `optional<T&>` because it has several very large and completely unavoidable differences with `optional<T>`.

Namely:

- it is spelled differently from `optional<T>` (trivially: it is spelled `T*`)
- it is differently constructible from `optional<T>` (you need to write `&e` in one case and `e` in the other)
- it has a different set of supported operations from `optional<T>`

The first of these is what required me to use `workaround<U>` instead of simply `optional<U>`, and the second required the ugly `if constexpr`s in order to be able to construct a `workaround<U>` in every context that one is being constructed.

The last of these I touched on a bit, but it's worth elaborating on. As I noted at the very beginning of the post, there _are_ operations in common between `optional<T&>` and `T*`... but there are even more operations that only apply to one or the other:

![Venn Diagram](/assets/img/optional-vs-ptr.png)

All the operations in the purple circle are highly relevant and useful to this problem. We want to have an optional reference, so it is useful to have the chaining operations that give us a different kind of optional, or to provide a default value, or to emplace or reset, or even to have a throwing accessor.

All the operations in the orange circle are highly _irrelevant_ to this problem and would be completely wrong to use. They are bugs waiting to happen. We don't have an array, so none of the indexing operations are valid. And we don't have an owning pointer, so neither `delete` nor `delete []` are valid. Nevertheless, these operations will actually compile -- even though they are all undefined behavior.

You'll note that I wrote "pattern matching" in both circles, differently, rather than putting them together in the combined set. That's not an oversight. Both [P1371](https://wg21.link/p1371) and Herb's [P2392](https://wg21.link/p2392) support matching both `optional<U>` and `T*`, but both papers (despite their many differences) recognize these types as having different semantics and match them differently:

* an `optional<U>` matches against `U` or `nullopt`, because that's what it represents precisely.
* a `T*` doesn't match against a `T`, rather it matches polymorphically. A `Shape*` could match against a `Circle*` or a `Square*`, but not against a `Shape`.

We don't have pattern matching in C++ yet, and we still won't in C++23. But eventually we will, and when we do, we'll want to be able to match on whether our optional reference actually contains a reference, or not. We do not need to match whether we're... holding a derived type or not. This is yet another operation that a `T*` won't do for us.

All in all, there is a much, much larger difference between `optional<T&>` and `T*` than there is between `vector<bool>` and `vector<almost_bool>`. And in every instance of this difference, `optional<T&>` is far more suited to the problem of dealing with an optional reference than `T*` is. `T*` is simply a very poor substitute.

This is true even if you know for sure you're dealing with an optional reference, in a non-generic context that doesn't need to try to select between `T*` and `optional<U>`. If you know for sure you need an optional reference, you want to return the implementation of optional reference that provides the most useful operations to the user and the one that provides the least pitfalls. That is, unequivocally, `optional<T&>`.

### What about `optional_ref<T>`?

The problem with `T*` as an optional reference is that it has such different semantics from `optional<T>` that basically every use of it requires a workaround. But what if we instead wrote a new type, dedicated to this problem: `optional_ref<T>`. Suppose `optional_ref<T>` were always an optional reference (it has a member `T*`, etc.), that is constructible the same way as `optional<T>` (from an lvalue of type `T`), and has all the same member functions.

Would we still need `optional<T&>` if we had `optional_ref<T>`?

Yes.

A hypothetical `optional_ref<T>` is a lot closer to solving the optional reference problem than `T*` is, but it still leaves a few things to be desired. First, as I pointed out with `T*`, it is spelled differently. This is obvious - its name is `optional_ref<T>` and not `optional<T&>`. The consequence of the different name is that you still need `workaround<T>` to exist - it's just that instead of choosing between `optional<T>` and `add_pointer_t<T>`, it now chooses between `optional<T>` and `optional_ref<remove_reference_t<T>>`. Still awkward.

Second, this duplicates a lot of effort fon the part of algorithms. `optional<T>`'s `map` and `value_or` are the same as `optional_ref<T>`'s `map` and `value_or`, but both types need both algorithms.

Maybe you don't care about how much work the implementer has to do for these types, but you probably do care about how much work you have to do on your end. And that leads into the third problem caused by the distinct spelling: how do _you_ write an algorithm that takes some kind of optional and does something with it? If optional values and optional references were both spelled the same, you could write a non-member `map` like so:

```cpp
template <typename T, typename F>
auto map(optional<T>, F) -> optional<invoke_result_t<F&, T&>>
```

Well, not exactly like that, because you probably don't want to take optional values by value, but it's kind of awkward in C++ to handle this particular kind of case (see [P2481](https://wg21.link/p2481) for some musings). But if we had `optional_ref<T>`, you would have to write two of everything yourself:

```cpp
template <typename T, typename F>
auto map(optional<T>, F)     -> workaround<invoke_result_t<F&, T&>>

template <typename T, typename F>
auto map(optional_ref<T>, F) -> workaround<invoke_result_t<F&, T&>>
```

Note that the return types are the same for both overloads, because of course they are.

And what did we gain from all of this duplication everywhere? It's unclear to me that we gained anything at all. Sure, if you're not used to the idea that `optional<T>` might be a reference type, it might seem superficially valuable to put that information in the name of the type itself. But it's a really bad tradeoff in terms of all the rest of the usage. `optional_ref<T>` is a much better optional reference than `T*`, but it's still a poor substitute.

### In conclusion

The ability to have `optional<T&>` as a type, making `optional` a total metafunction, means that in algorithms where you want to return an optional value of some computed type `U`, you can just write `optional<U>` without having to worry about whether `U` happens to be a reference type or not. This makes such algorithms easy to write.

Without `optional<T&>`, we either have to reject reference types in such algorithms (as `optional<T>::transform` currently does) or workaround them by returning a `T*`. But `T*` has different construction semantics from `optional<T>` (so algorithms constructing such a thing have to have more workarounds) and it has a very different set of provided operations. In particular, all the operations provided by `optional<T>` but not by `T*` are useful in the context of having an optional reference, whereas all the operations provided by `T*` but not by `optional<T>` are completely wrong and are simply bugs waiting to happen.

`T*` seems like it basically is `optional<T&>`. After all, they have many properties in common, and the latter is certainly implemented in terms of the former. But `T*` makes for a very poor solution to the problem of wanting an optional reference. Even an `optional_ref<T>` that solves the problem of having all the right functionality and none of the wrong functionality still can't quite offer everything that `optional<T&>` could.

`optional<T&>` is unequivocally the best optional reference.
