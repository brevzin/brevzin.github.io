---
layout: post
title: "Prefer <code class=\"language-cpp\">views::meow</code>"
category: c++
tags:
 - c++
 - c++20
 - c++23
 - ranges
---

With the adoption of Ranges in C++20 (and with a lot of new additions in C++23), we have a lot of new, composable, range-based algorithms at our disposal. There are, however, several ways to spell the usage of such algorithms:

```cpp
vector<int> v = {1, 2, 3};
auto square = [](int i){ return i * i; };

auto a = v | views::transform(square);
auto b = views::transform(v, square);
auto c = ranges::transform_view(v, square);
```

Which should you prefer?

The answer is either `a` or `b`, never `c`.

## `views::meow` is the algorithm

`views::meow` is the actual, user-facing algorithm. It takes a `viewable_range`, and possibly some other arguments, and produces a new `view` whose behavior meets the goal of the algorithm. In the above example, `views::transform` takes a range (`v`) and a unary function (`square`) and produces a view whose elements are the result of applying that function to every element of the original range.


> The use of `meow` here is as a [metasyntactic variable](https://en.wikipedia.org/wiki/Metasyntactic_variable). Other people might use `foo` or some other more obvious placeholder like `XXX`. I somehow picked up this practice from STL and Tim Song, even though my avatar for this blog is a dog.
{: .prompt-info }

In the typical case, the way to _implement_ `views::meow` is by creating a new type, `ranges::meow_view`, that wraps the original view and those other arguments and has the expected behavior. For an algorithm like `transform`, this is [quite simply](https://eel.is/c++draft/range.transform#overview-2) what it does:

> Given subexpressions E and F, the expression `views​::​transform(E, F)` is expression-equivalent to `transform_­view(E, F)`.

But this isn't actually the case for all range adaptors, and it need not even be the case for `views::transform`.

## Not all wrapping is necessary

Consider one of the new C++23 adaptors: `views::as_const`. The job of `views::as_const(E)` (or `E | views::as_const`, if you prefer), is to produce a range whose elements you cannot mutate. If `E` were a range of `int&`, then `views::as_const(E)` would give you a range of `int const&`. It does so by returning a `ranges::as_const_view(E)`.

But what if `E` were already a range of `int const&`? In that case, `E` is already a constant view - we don't need to do any work to produce a constant view out. So `views::as_const(E)` can simply return... `E`. `ranges::as_const_view(E)` cannot do that, since that's a type - but `views::as_const(E)` can, since it's an algorithm. It can make smarter, more efficient choices.

The same holds for `views::as_rvalue(E)` (which simply propagates `E` if it's already a range of rvalues) and `views::common(E)` (which likewise propagates `E` if it is already a common view). In these cases, the wrapping may not even be valid - `views::common(E)` gives you back a common view regardless of whether `E` is common or not, but `ranges::common_view(E)` requires `E` to be non-common.

## More efficient implementations

In other cases, it is possible for an algorithm to produce a more efficient implementation - where efficient isn't just a runtime behavior, it's also a compile-time one. Instantiating fewer templates, with less wrapping, means faster compile time - and likely better optimization outcomes, since there's less work to do.

There are several cases of this in the standard library as well:

```cpp
void f(span<int> s) {
    auto a = s | views::take(1);
    auto b = s | views::drop(1);
    auto c = s | views::as_const;
}
```

In this example, `ranges::take_view(s, 1)`, `ranges::drop_view(s, 1)`, and `ranges::as_const_view(s)` would all be valid ranges, that all have the desired behavior of the algorithm. They are all semantically correct. But they all require further instantiations, with more overhead (that is hopefully optimized out).

But that's not what `views::take`, `views::drop`, and `views::as_const` do. Instead, `a` and `b` are also actually objects of type `span<int>` (constructed appropriately) and `c` is a `span<int const>`. That's strictly better than the alternative.

Likewise, consider:

```cpp
auto r = /* some bidirection range */;

auto rev1 = views::reverse(r);
auto rev2 = views::reverse(rev1);
```

`rev2` is `r`, reversed twice. `views::reverse(E)` recognizes when `E` is itself a reversed view, and short-circuits - `rev2` is simply `r` (or, more precisely, `views::all(r)`). But had we used `ranges::reverse_view(r)` and `ranges::reverse_view(rev1)`, that's not the behavior we'd get - instead we'd have ended up with a `ranges::reverse_view<ranges::reverse_view<V>>`. Double-wrapped, instead of not-wrapped.

Even in the original `transform` example, it is possible to do better:

```cpp
r | views::transform(f) | views::transform(g)
```

You could imagine that an implementation could recognize that it's adapting a `transform`-ed range, and internally compose the two functions - so that internally this becomes:

```cpp
r | views::transform(f >> g)
```

That's not what `views::transform` does in C++20, and indeed it is explicitly specific to _not_ do that. But if you just use `views::transform`, then perhaps it could in the future.

## `ranges::meow_view` is an implementation detail

The right way to think about `ranges::meow_view` is that it's simply an implementation detail of `views::meow`. Sometimes the latter gives you the former, sometimes it gives you something else. But you should really think about `views::meow` as simply giving you _something_ that satisfies the semantics of the algorithm. `views::meow` also supports piping, so it's just more convenient to begin with.

And lastly, `views::meow(E)` is just shorter than `ranges::meow_view(E)`. So even if there weren't several compelling reasons to prefer it already, it's also less to type. So if I haven't convinced you yet, there's also this.

The question might be, at this point, why do we even specify `ranges::meow_view` to begin with? And there, I think, the answer simply has to do with complexity. I think users should consider these types as exposition-only, but it is helpful for the _implementations_ to have all their behavior specified. A lot of it is subtle. Plus a lot of adaptors expose their internals (via `base()` or `pred()`, etc.) so it's not just a question of `views::transform(E, F)` yielding a range with particular semantics, it's also a question of how _else_ you can interact with the result. As tedious as it is to provide these specifications, I do have to grudgingly accept that they provide some value.

## Surely there's at least some use for explicit `ranges::meow_view`?

There is precisely two situations where it makes sense to explicitly use `ranges::meow_view` over `views::meow`. The obvious one is: when you're implementing `views::meow`. But that's a boring answer.

The more interesting answer is: when you're implementing a different view. One example here might be `zip_transform`. `views::zip_transform(F, Es...)` is a range that whose elements are the result of `F(es...)` for all the elements `es...` of `Es...`. This is quite closely related to `zip`, and indeed is very similar to:

```cpp
views::zip(Es...) | views::transform(hof::unpack(F))
```

(see [here](https://www.boost.org/doc/libs/master/libs/hof/doc/html/include/boost/hof/unpack.html) for `hof::unpack`).

How would you implement `views::zip_transform`? Fundamentally, you're still iterating over all the ranges at the same time - that's still a `zip`. And, indeed, the easiest way to implement this is to, internally, use `ranges::zip_view` (as you can see [here](https://eel.is/c++draft/range.zip.transform.view)):

```cpp
template <move_constructible F, input_range... Views>
    requires /* bunch of other stuff */
class zip_transform_view : public view_interface<zip_transform_view<F, Views...>> {
    movable_box<F> fun_;
    zip_view<Views...> zip_;
};
```

Although since this is the standard library, we don't just dereference `zip_.begin()` (producing a `std::tuple`) and then use `std::apply` on that result - instead we sidestep the construction of the `std::tuple` and get access to the underlying `std::tuple<iterator_t<Views>...>` directly.

But the point here is - having a member `zip_view` makes it easier to implement `zip_transform_view`.

If you're not implementing a view, there's probably no other reason to explicitly write `ranges::meow_view`.

## Conclusion

Always prefer `views::meow` over `ranges::meow_view`, unless you have a very explicit reason that you specifically need to use the latter - which almost certainly means that you're in the context of implementing a view, rather than using one.
