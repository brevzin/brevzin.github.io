---
author: brevzin
title: "What's so hard about views::enumerate?"
html_title: What's so hard about views::enumerate?
category: c++
tags:
  - c++
  - c++23
  - ranges
---

Sometimes, we want more than to just iterate over all the elements of a range. We also want the index of each element. If we had something like a `vector<T>`, then a simple `for` loop suffices [^int]:

```cpp
for (int i = 0; i < vec.size(); ++i) {
    // use i or vec[i]
}
```

But for a range that can't be indexed like this (or a range for which indexing like this means something else entirely, like `map<int, T>`), we need to do it differently.

You could write:

```cpp
int index = 0;
for (auto&& elem : r) {
    // use index or elem
    ++index;
}
```

But that's a bit fragile, since if you added a `continue`, now suddenly your `index` is wrong. This would be better:

```cpp
int index = 0;
for (auto&& elem : r) {
    SCOPE_EXIT { ++index; };
    // use index or elem
}
```

But that's an awkward construction. And it's also limited to imperative uses like this - if you wanted to do further work on this new range with the indices, you'd need something more.

To do that, we have the algorithm `views::enumerate` (other names for this algorithm include `zip_with_index`, `with_index`, and `indexed`). That allows:

```cpp
for (auto&& [index, elem] : views::enumerate(r)) {
    // ...
}
```

Which would be correct by construction, just yields the right indices on demand, and can be passed through to further algorithms.

So what's so hard about `views::enumerate`?

Only two things:

1. Is enumerate [just a zip](#zip)?
2. What should its [reference type be](#reference)?

## We have `zip` and `iota`, do we need `enumerate`? {#zip}

I'll start with the easier question. We can already (in C++23) write `zip(iota(0), r)`, do we really need `enumerate(r)`? That is:

```cpp
inline constexpr auto enumerate =
    [](viewable_range auto&& r){
        return zip(iota(0), FWD(r));
    };
```

This would allow `enumerate(r)` but not `r | enumerate`. But we can change that too, thanks to C++23's [P2387](https://wg21.link/p2387). Fully qualifying everything, for clarity:

```cpp
struct Enumerate
    : std::ranges::range_adaptor_closure<Enumerate>
{
    template <std::ranges::viewable_range R>
    constexpr auto operator()(R&& r) const {
        return std::views::zip(std::views::iota(0), (R&&)r);
    }
};

inline constexpr Enumerate enumerate;
```

That's not so bad, and it does give you the right values if you iterate sequentially. But it is missing some useful functionality.

Consider:

```cpp
std::string letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
auto e = enumerate(letters);
auto z = e.back();
```

It would make sense for this to work and be cheap: `letters` is a random-access, sized range. We know it has size `26` [^alphabet] and we can efficiently get the last element, so we should be able to get `(25, 'Z')` as the value for `z` too.

And it sure seems like the above implementation should give it to us. But it doesn't. To explain why, we need a quick digression on cardinality.

> In C++20, ranges are either sized or not. If a range can provide its size in constant time, it's a sized range. Otherwise, it's not. This size must be finite - C++20 doesn't really have a notion of infinite ranges. They exist, and the standard library even provides `std::unreachable_sentinel` (which, as the name suggests, is in fact unreachable). But the library has no means to take advantage of this information.
>
> range-v3 had a more complex notion of range sizing that it called **cardinality**. A range has a cardinality that is either a non-negative constant (e.g. `array<int, 3>` has a cardinality of `3` and `views::empty<int>` has a cardinality of `0`, this is for types whose size is fixed), `finite` (this is a range whose size is known to not be `infinite`, but may not be sized), `unknown` (shrug), or `infinite`. So `views::iota(0, 10)` has a cardinality of `finite` (and a size of `10`) while `views::iota(0)` has a cardinality of `infinite`. Note that `finite` does not imply sized: `r | views::take(5)` has cardinality `finite` (we know for sure that this range isn't `infinite`), but if `r` isn't a sized range, then that's all we can say about it. An example of a range with `unknown` cardinality is `r | views::take_while(f)`. If `r` is `finite`, then this is certainly `finite` too. But if `r` is `infinite`, the result could still actually be `finite`. We just don't know.
{: .prompt-info }

With range-v3, because we know that `views::iota(0)` is `infinite`, we could still consider `views::zip(views::iota(0), letters)` to be a sized range of size 26 [^infinity], and we could know that we can safely add 25 to the `views::iota(0).begin()`. Our implementation of `enumerate(letters)` is a sized range, which would allow `z.back()` to work.

Or at least, this should be the case. range-v3's implementation of `zip` does provide the correct cardinality (`finite`) but still isn't sized [^sized_enumerate]. The current implementation is only sized when [all of the underlying ranges are](https://github.com/ericniebler/range-v3/blob/247e6813451c78bfbf7f9d4b394bbb0b31aaf243/include/range/v3/view/zip_with.hpp#L351-L366):

```cpp
// with range-v3
namespace rv = ranges::views;
auto e = rv::zip(rv::iota(0), letters);
using E = decltype(e);

// passes, as expected
static_assert(ranges::range_cardinality<E>::value == ranges::cardinality::finite);

// fails, unfortunately
static_assert(ranges::sized_range<E>);
```

But in C++20 ranges, we don't _know_ that `views::iota(0)` is `infinite` [^unreachable], so we don't _know_ that `views::zip(views::iota(0), letters)` has size 26. For all we know, `views::iota(0)` could run out of elements at any time. As a result, this range is random-access but it is _not_ sized, so `z.back()` doesn't exist.

So we need to do a little more work - we need to ensure that `enumerate`-ing a sized range gives us a sized range back:

```cpp
struct Enumerate
    : std::ranges::range_adaptor_closure<Enumerate>
{
    template <std::ranges::viewable_range R>
    constexpr auto operator()(R&& r) const {
        if constexpr (std::ranges::sized_range<R>) {
            auto d = std::ranges::distance(r);
            return std::views::zip(std::views::iota(0, d), (R&&)r);
        } else {
            return std::views::zip(std::views::iota(0), (R&&)r);
        }
    }
};

inline constexpr Enumerate enumerate;
```

We can't just do `zip(iota(0, distance(r)), (R&&)r)` because we need to ensure we get the range's size _before_ the range is moved from (if the second argument happens to be evaluated first).

With the above extension, `z.back()` will now work. It took a bit of a journey to get here, but that's still just 15 lines of not-exactly-dense code. Good eonugh?

Now there's one more thing. I didn't really want to talk about integer types [^int]. And I still don't. I especially don't want to talk about integer signed-ness. But I _do_ need to talk about integer width.

This is covered in [P2214](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2022/p2214r2.html#enumerates-first-range), but the problem with using `views::iota` for `enumerate`'s first range is determining what `iota`'s `difference_type` needs to be. The problem here, in short, is that `iota` needs to pick a `difference_type` wide enough to actually compute the difference between its elements. For `iota_view<int, int>`, that `difference_type` cannot be `int` - since we cannot know if that's wide enough. So it's actually `int64_t`. But then what's `iota_view<int64_t, int64_t>`'s difference type? Well, we have `__int128`. But at some point we can't keep going one integer wider.

But for `enumerate(r)`, specifically, we don't have to worry about trying to pick the right `difference_type` since we know `r`'s `difference_type` is already wide enough (or, at least, it has to be - and if it's not, that's `r`'s problem, not `enumerate`'s).

The issue with using `views::iota` here is ultimately that we will get a `difference_type` that's too big. If what we're `views::enumerate`-ing is a `std::vector<T>`, for instance, and we use `views::iota`, then we'll get a `difference_type` of `__int128`. But we don't need an integer that wide - `size_t` suffices (or `ptrdiff_t`, if we wanted to be signed). What this means in practice is that algorithms that use the range's `difference_type` to do math (the simplest example might be `ranges::count` and `ranges::count_if`, but they're hardly the only ones) are going to be, potentially, less efficient than ideal.

That's probably still good enough for most cases, and it's at least _correct_, but if we're talking about the standard library, it'd be good to ensure that we get this correct. Whether that's writing a special-case version of `views::iota` where we tell it what its `difference_type` should be and `zip` with that (which is what range-v3 does) or write a dedicated `enumerate_view`.

## What should `enumerate`'s reference type be? {#reference}

Before really diving into this question, I need to do somewhat of a long digression with some background. If you don't care, you can skip to [here](#options).

### Background

The most important associated type of a range is its `reference` [^reference]. That's the type you get when you dereference the iterator, so it's what you interact with directly. Most algorithms _only_ need to interact with this type.

The next most important associated type of a range is its `value_type`. This is supposed to be an independent value semantic type. Most people think of this as being _just_ `std::remove_cvref_t<reference>`. And, indeed, that is nearly always the case. The overwhelmingly most common range types fit into one of these three rows:

|range type|`reference`|`value_type`|
|-|-|-|
|`vector<int>`|`int&`|`int`|
|`vector<int> const`|`int const&`|`int`|
|`ranges::iota_view<int, int>`|`int`|`int`|

One example of an algorithm that actually uses `value_type` would be `min`, which might be implemented like so:

```cpp
template <ranges::input_range R,
          indirect_strict_weak_order<iterator_t<R>> Comp>
constexpr auto min(R&& r, Comp comp) -> ranges::range_value_t<R> {
    auto f = ranges::begin(r);
    auto l = ranges::end(r);

    ranges::range_value_t<R> best = *f;
    for (++f; f != l; ++f {
        if (comp(*f, best)) {
            best = *f;
        }
    }
    return best;
}
```

Consider what the call to `comp` is actually doing. It takes two parameters: `*f` is the range's `reference` type while `best` is an _lvalue_ of the range's `value_type`. So what does `comp` have to look like?

Or, to put the question more precisely, if I were to try to write a _non-generic_ predicate, what type should it take for both parameters? That is, how do I determine what `U` is here:

```cpp
using U = /* ??? */;
auto best = ranges::min(r, [](U lhs, U rhs) { return /* ... */ });
```

`U` here is the range's _common reference_ type [^common_reference]. It's the one type that you use if you want a non-generic callable. And, in the above table, determining the common reference bewteen the `reference` and `value_type&` (note the `&`) is very straightforward - it's just the `reference` type.

But what happens when we introduce _proxy_ references?

|range_Type|`reference`|`value_type&`|`common_reference`|
|-|-|-|-|-|
|`vector<int>`|`int&`|`int&`|`int&`|
|`vector<int> const`|`int const&`|`int&`|`int const&`|
|`ranges::iota_view<int, int>`|`int`|`int&`|`int`|
|`vector<bool>`|`vector<bool>::reference`|`bool&`|????|
|`ranges::zip_view<vector<int>>`|`tuple<int&>`|`tuple<int>&`|????|

This is where things get tricky.

We need a type that is convertible from `reference` and `value_type&`. For `vector<bool>`, that ends up being bool `bool` (notably, we took a proxy reference and an lvalue language reference and ended up with something with no reference semantics). For `zip_view<vector<int>>`, this is `tuple<int&>` (which wasn't actually constructible from `tuple<int>&` before, but will be in C++23).

### Options

It's okay if you didn't understand that. The point is that a range needs to have a `reference` and `value_type`, and that there needs to be some type (not necessarily distinct from those) called the `common_reference` which is convertible from `reference` and `value_type&` that is preferably as reference-like as possible.

Now, let's talk about what the `reference` type for `enumerate` be. There are basically two options (and I'm back to just using `int` for the index type):

```cpp
// a struct with named members
struct reference {
    int index;
    ranges::range_reference_t<R> value;
};

// a tuple
using reference = tuple<int, ranges::range_reference_t<R>>;
```

If we just [used zip](#zip) (with the custom version of `views::iota` as described above), we'd end up with the `tuple`. But if we're going to write a dedicated `views::enumerate` adaptor, we could have a dedicated `reference` type.

Which is better?

Now, a struct with named members should really be the default choice over `std::pair` or `std::tuple`, because having meaningful names is a lot better than... not having meaningful names. So why would we even consider the `std::tuple` option?

First, let's also fill in the `value_type`:

```cpp
// struct with named members
struct value_type {
    int index;
    ranges::range_value_t<R> value;
};

// a tuple
using value_type = tuple<int, ranges::range_value_t<R>>;
```

Now, let's consider what properties these types need to have.

`reference` and `value_type` need to be appropriately convertible between each other and have a corresponding `common_reference`. That's... doable. Let's start implementing this:

```cpp
template <typename T>
struct enumerate_result {
    int index;
    T value;

    // regular constructor, since this can't be an aggregate
    template <convertible_to<T> U>
    enumerate_result(int index, U&& value)
        : index(index)
        , value(FWD(value))
    { }

    // converting constructors (these should all be conditionally explicit)
    template <typename U>
        requires constructible_from<T, U&>
    enumerate_result(enumerate_result<U>& r);
    template <typename U>
        requires constructible_from<T, U const&>
    enumerate_result(enumerate_result<U> const& r);
    template <typename U>
        requires constructible_from<T, U&&>
    enumerate_result(enumerate_result<U>&& r);
    template <typename U>
        requires constructible_from<T, U const&&>
    enumerate_result(enumerate_result<U> const&& r);
};
```

Yet another nice use-case for something in [P2481](https://wg21.link/p2481).

That gets us the conversion behavior we need, but we also need to provide a specialization of `std::basic_common_reference` [^common_reference], because otherwise we have the issue that the `common_reference` of `enumerate_result<int>&` and `enumerate_result<int&>` is `enumerate_result<int>`, when it should be `enumerate_result<int&>`.

Also doable. We may want to consider adding comparisons too. Perhaps conversions to `std::pair<int, U>` and `std::tuple<int, U>` too? Those would surely be useful in some contexts. Should `std::apply` work for this type?

At this point we've mostly re-implemented `std::pair<T, U>`, just with different field names. Which is pretty tedious specification and implementation, but all of these things exist for a reason to solve a particular problem. This isn't a question of how hard is it to write a type with two members - it's a question of how hard it is to write a small family of types that are properly inter-convertible (`reference`, `value_type`, `common_reference`, `const_reference`, and `rvalue_reference`).

But going through that effort actually still isn't quite sufficient. Consider:

```cpp
std::string letters = /* ... */;

auto m = letters
       | std::views::enumerate
       | std::ranges::to<std::map>();
```

That's a reasonable thing to want to write, to get: to enumerate a range and then put it into some kind of associative container (this _specific_ example, maybe not so much, since `letters` is already indexable even more efficiently than a `std::map` is, but imagine a more complex transformation in here somewhere, plus maybe some filtering).

In order for this to work with `std::map`, `views::enumerate` had to (until recently) be specifically a range whose `value_type` was `std::pair<T, U>`. Now it can also be a range of `std::tuple<T, U>` ([P2165](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2022/p2165r4.pdf)). But while the standard library containers have become more flexible (and could be extended further to support `enumerate_result<T>`), user-defined associative containers have not.

### Disposition

Thus, the question is not simply: should `enumerate` provide a range whose `reference` and `value_type` have named members, or should these types be specializations of `std::tuple`?

The question really is: is it worth the added complexity of adding another `std::pair` to the standard library and modifying all the associative containers to handle it, knowing that other associative containers (like abseil's and Boost's) would not?

I really don't think the names are worth it. Part of the reason I don't think the names are worth it is the cost of specifying all of this stuff just for `views::enumerate`. It's a very useful range adaptor, but it's not _that_ useful. Using a `std::tuple` at this point is, basically free.

But part of the reason is also that the names, in this particular context, really aren't even all that that valuable. If I'm enumerating a range and directly consuming it, I'm always going to write this:

```cpp
for (auto&& [index, elem] : views::enumerate(r)) {
    // ...
}
```

And while I can't use structured bindings directly in a lambda for `transform` or a `filter`, I think the better answer there is actually to just change the language so that I can actually use structured bindings in a function parameter list.

Sure, there's a chance that I might get the order wrong. If the underlying range's `reference` type isn't numeric, then whatever I'm doing probably won't compile. But in the case where the two types are possible to interchangeable, this could very well lead to a subtle runtime bug.

But this *is* the same order that Python uses. And Rust. And D. And it's really the obvious choice for ordering, if you think about `views::enumerate` as producing a numbered list: the number goes first. It's not the universal ordering though, unfortunately (Kotlin, Clojure, Swift, and Go all put the index first, but JavaScript, Scala, C#, and Ruby put the index second, for instance). But I find it notable that many of these languages do not have the complex type requires that C++ Ranges do, yet still just use a tuple (D and Kotlin at least have a _named_ tuple).

Given a choice between `std::tuple` and a struct with named members, you should prefer the struct with named members - unless there's a fairly compelling reason otherwise. That is the right default. In this particular case, the names have far less value than they might in other contexts and also the cost for providing them is quite high. So in this particular case, I believe the right answer for `views::enumerate` is to have its `reference` and `value_type` be `std::tuple`s.

## Bonus Problem: Structured Bindings Strike Again

I said there were only two problems, but this one isn't really specific to `views::enumerate` in any way, but it will certainly come up.

Consider:

```cpp
std::vector<std::string> names = {"fiona", "eleanor"};

for (auto [index1, name1] : views::enumerate(names)) {
    // #1
}

for (auto const& [index2, name2] : views::enumerate(names)) {
    // #2
}
```

What is the type of `name1` and what is the type of `name2`? The answer to this question is actually independent from the answers to either the [zip](#zip) or [reference](#reference) questions.

The "obvious" answer is that `name1` is a `string` (because `auto`) and `name2` is a `string const&` (because `auto const&`). That's certainly what it looks like in these loops! The spelling of bindings does suggest that the introducer distributes over the bindings. That is, `auto [a, b]` looks like it behaves like `[auto a, auto b]` and `auto const& [c, d]` looks like it behaves like `[auto const& c, auto const& d]`. Indeed, the visual of distribution is so striking that [Pattern Matching](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2020/p1371r3.pdf) is running with the idea with how they're suggesting introducing bindings, where `let [x, y]` does very much mean `[let x, let y]`.

But that's _not_ how structured bindings work. Let's just focus on the first element of the enumeration, stick with named members, and desugar the structured binding declarations:

```cpp
struct enumerate_result {
    int index;
    std::string& value;
};

std::vector<std::string> names = {"fiona", "eleanor"};

auto __t1 = enumerate_result{.index=0, .value=names[0]};
auto& index1 = __t1.index;
auto& name1 = __t1.value;

auto const& __t2 = enumerate_result{.index=0, .value=names[0]};
auto& index2 = __t2.index;
auto& name2 = __t2.value;
```

The `auto` and `auto const&` only apply to the declaration of this invisible object (which I've named `__t1` and `__t2`). All the bindings themselves are _basically_ `auto&` (the wording here is slightly more complicated, but for our purposes here, is sufficiently accurate).

If you work through what this actually manes, _both_ `name1` _and_ `name2` are `std::string&`. Both are mutable, lvalue references to `std::string`. Both are aliases for `names[0]`. Even though `name1` looks like it was declared with `auto`, it's a reference. Even though `name2` looks like it was declared with `auto const&`, it's a mutable reference.

This is surprising and unlikely to be the desired behavior. It bears repeating, though, that this isn't a `views::enumerate` problem or even a `views::zip` problem. It's really a structured bindings problem.

Is this fixable?

I'm not really sure. Having `name2` be mutable instead of const probably isn't a huge problem - if you expected it to be const, you're probably also not trying to mutate it, so you're fine. Having `name1` be a reference instead of a copy is something that assuredly some code relies on (both performance-wise not actually making that copy and also semantically relying on `name1` being a reference to within `names`) while also is likely to have lead to bugs (e.g. if the loop mutates `name1` for convenience thinking the loop owns its own string).

Just something to think about.

----

[^int]: In this blog, I'm just going to use `int` as the index type for all ranges. This isn't the correct type - the index type should be a property of the range (specifically either `range_size_t<R>` or `range_difference_t<R>` depending on your approach to signed-ness). But integer types isn't the point of this blog post, so I'm just using `int` for simplicity.
[^alphabet]: Assuming I typed the alphabet correctly. I did not check.
[^infinity]: The merged cardinality of a `finite` and `infinite` range is a `finite` range. We know the size is 26 because the minimum size of 26 and infinity is 26, except for very small values of infinity.
[^sized_enumerate]: This is certainly implementable. The constraint right now is that all the underlying ranges satisfy `sized_range`. But we can filter down to _just_ the non-`infinite` ranges: if all the non-`infinite` ranges satisfy `sized_range`, then the `size` is the minimum of all the sizes of the `finite` ranges. PRs welcome!
[^unreachable]: Eric Niebler and Casey Carter were never quite happy with the range-v3 model of cardinality, so as far as I'm aware it was never actually pursued for standardization. We _could_ potentially introduce infinite ranges as simply those ranges whose sentinel is `std::unreachable_sentinel_t` - but it would take a lot of work to carefully work through the consequences.
[^reference]: This really is an unfortunate name in retrospect. A range's `reference` type need not actually be any kind of reference (neither language reference nor proxy reference nor even a type with any kind of reference or pointer semantics at all). A range's `reference` type could be `int` (e.g. `views::iota(0, 10)` is such a range). I wish in retrospect that it was `element` or `item`.
[^common_reference]: `common_reference_t` is the most complex type trait in the standard library by a mile. Outside of trivial cases, nobody can actually tell you what the common reference of two types is. Eric Niebler wrote a long series of blog posts in 2015 building up the motivation for this, which you can find in [0](http://ericniebler.com/2015/01/28/to-be-or-not-to-be-an-iterator/) [1](http://ericniebler.com/2015/02/03/iterators-plus-plus-part-1/) [2](http://ericniebler.com/2015/02/13/iterators-plus-plus-part-2/) [3](http://ericniebler.com/2015/03/03/iterators-plus-plus-part-3/).
