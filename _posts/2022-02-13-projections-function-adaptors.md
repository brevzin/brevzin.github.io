---
layout: post
title: "Projections are Function Adaptors"
category: c++
tags:
  - c++
  - c++20
  - ranges
---

There was a question recently on StackOverflow where a user was confused about the purpose of projections in a way that I think is fairly common. They wanted to do something like this:

```cpp
struct Person {
    std::string first;
    std::string last;
};

std::vector<Person> people = { /* ... */ };
std::vector<std::string> r_names;
std::ranges::copy_if(
        people,
        std::back_inserter(r_names),
        [](std::string const& s) { return s[0] == 'R'; },
        &Person::last);
```

[Obligatory link]({% post_url 2022-02-06-output-iterators %}) to post about `std::back_inserter`, or output iterators more generally.

The goal here was to put all the last names that start with `'R'` into `r_names`. But this ends up not compiling. Why not?

I could paste the compile error, but I'm sorry to say that it's not very useful (unless you already know the problem). But if we could actually get good compile errors, the one that this would emit would be:

> error: `std::back_inserter(r_names)` does not satisfy `std::output_iterator<Person&>`

To which the user in question would be very confused. Of course `std::back_inserter(r_names)` isn't an output iterator for `Person`, the goal was to output `std::string`s! Isn't that the point of `&Person::last`? Why is the projection being ignored?

The reason for this user's error is a common misunderstanding of the point of projections. If you take away one thing from this blog post, it should be this:

> Projections do not change the algorithm. Projections are a simply convenient way to adapt the algorithm's predicate (or function).

### Projections do not change the algorithm

What do I mean by this? The goal of `std::ranges::copy_if` is to copy some (possibly no) elements of a source range into an output iterator. When you see:

```cpp
std::ranges::copy_if(people, o, ...)
```

That algorithm is copying objects of type `Person` into `o`. What comes next (the predicate and the projection) only affect _which_ objects of type `Person` are copied. They do not change the crux of the algorithm. They do not change what the source range being copied is.

Note also that `std::ranges::copy`, an algorithm that copies all of the elements of a source range into the output iterator, does not take a projection argument at all. It does not, because it also does not take any kind of function argument. As a result, it doesn't need a projection either, because...

### Projections are function adaptors

Let's now correct the original example into something that compiles (although isn't yet what was actually wanted): by providing an output iterator that accepts people.

```cpp
std::vector<Person> r_people;
std::ranges::copy_if(people,
    std::back_inserter(r_people),
    [](std::string const& s) { return s[0] == 'R'; },
    &Person::last);
```

This is one way to write a call that copies all the `Person` objects whose last name starts with `'R'`. But you could write it differently too, by simply combining both operations into a single lambda:

```cpp
std::ranges::copy_if(people,
    std::back_inserter(r_people),
    [](Person const& p) { return p.last[0] == 'R'; });
```

These two calls do exactly the same thing.

That's because `ranges::copy_if(r, o, pred)` copies every element `e` in `r` such that `pred(e)` is `true`. Whereas `ranges::copy_if(r, o, pred, proj)` copies every element `e` in `r` such that `pred(proj(e))` is `true`.

We could write this differently still, by separating out `pred(proj(e))` into a distinct function that we can invoke on `e`. That is, some new function `f` such that `f(e)` is `pred(proj(e))`. That's your most basic kind of function composition: taking two functions and producing a new one that invokes the first and then the second. This is such a fundamental operation that in Haskell it exists as a language feature that takes just one character to compose functions: `pred . proj` (since the mathematics symbol for function composition is `∘`).

In C++, we don't have function composition as a language feature. It is, instead, a library feature. You can find it, for instance, in Boost.HOF under the name [`hof::compose`](https://www.boost.org/doc/libs/1_67_0/libs/hof/doc/html/include/boost/hof/compose.html). This other formulation _also_ does the exact same thing as the other two:

```cpp
std::ranges::copy_if(people,
    std::back_inserter(r_people),
    hof::compose([](std::string const& s) { return s[0] == 'R'; }, &Person::last));
```

Put differently, every algorithm in the standard library that accepts a unary predicate and a projection, such that we have `algo(..., pred, proj)` can have its projection dropped without any loss of functionality because users can do the function composition themselves and invoke it as `algo(..., hof::compose(pred, proj)))`.

### How to change the algorithm

Let's take a look at a different example, that hopefully demonstrates better the use of projections (or function adaption in general) and the difference between changing the predicate of an algorithm and changing the source of an algorithm.

Consider a two-dimensional `Point` class, which is lexicograhically ordered by its `x` coordinate and then its `y` coordinate:

```cpp
struct Point {
    int x;
    int y;

    auto operator<=>(Point const&) const = default;
}

std::vector<Point> points = {
    {1, 2},
    {1, 4},
    {2, 1},
    {3, 2},
    {0, 5},
    {6, 0}
};
```

If I want to take the smallest or largest points, I can do:

```cpp
Point smallest = std::ranges::min(points); // (0, 5)
Point largest  = std::ranges::max(points); // (6, 0)
```

By default, `ranges::min` and `ranges::max` both use `std::ranges::less{}` as the comparison object and identity as the projection. Both algorithms always give you an object of the source range's value type -- regardless of the predicate or the projection. While it may be pretty obvious that `ranges::min(points, pred)` is always a `Point` (assuming it compiles), it's really worth stressing again that `ranges::min(points, pred, proj)` is also always a `Point` (again, assuming it compiles).

Why might we want to use projections? Well, we might not want the smallest point lexicographically. We might want the point with the smallest Y-coordinate. We could do that by providing a custom predicate:

```cpp
// this is the Point (6, 0), not the int 0
Point point_with_smallest_y = std::ranges::min(points, [](Point const& a, Point const& b){
    return a.y < b.y;
});
```

And that's a perfectly fine approach. I have before, and will continue to in the future, write code like this. But it does conflate two different things: the `<` part and the repeated `Point.y` part. Repeating is a complete non-issue when it's a single-character member name, but the thing we're comparing could be arbitrarily complex.

Projections allow us to separate the concerns:

```cpp
// still (6, 0)
Point point_with_smallest_y2 = std::ranges::min(points, std::ranges::less{}, &Point::y);
```

You can read this as computing the smallest value in `points` _by_ `&Point::y`, or using the _key_ `&Point::y` (as Swift and Python would call this, respectively).

Before, we were applying a projection to a unary predicate. Here, we're applying a projection to a _binary_ predicate. What does that mean? Well, instead of comparing `pred(lhs, rhs)` we're first applying the projection to _both_ arguments. That is, we're looking at the result of `pred(proj(lhs), proj(rhs))`.

This isn't the most simple kind of function composition, but it is still a form of function adaptor. [Boost.HOF](https://www.boost.org/doc/libs/1_78_0/libs/hof/doc/html/include/boost/hof/proj.html) has us covered there too, with a very appropriately named adaptor:

```cpp
// also still (6, 0)
Point point_with_smallest_y3 = std::ranges::min(points, hof::proj(&Point::y, std::ranges::less{}));
```

Earlier, I used the adaptor `hof::compose`, which has the meaning:

```cpp
hof::compose(f, g)(x) == f(g(x))
```

Here, the adaptor `hof::proj` has the meaning

```cpp
hof::proj(p, f)(xs...) == f(p(xs)...)
```

In the unary case, `hof::proj(g, f)(x) == f(g(x)) == hof::compose(f, g)`. That is, just the order of arguments reversed.

But okay, I just showed three different ways to get the `Point` with the smallest Y coordinate, but that's still getting the smallest `Point`. What if you wanted to just get the smallest Y coordinate? After all, this section is titled "How to change the algorithm" and I have not yet shown any change in the algorithm!

Of course, we could just do this:

```cpp
int smallest_y = std::ranges::min(points, std::ranges::less{}, &Point::y).y;
assert(smallest_y == 0);
```

But this is again the same kind of repetition I mentioned earlier: we're using our projection twice, once as an argument into `ranges::min` and again on the result of `ranges::min`. We don't have to do that. If we want the smallest Y coordinate, the way to do that is to have a range not of `Point` but instead have a range of Y coordinates.

That's not a function adaptor anymore, which means that projections can't help us. Projections cannot change the source range, which is what we need to solve this problem. The way to change the source range is to use a _range_ adaptor:

```cpp
int smallest_y2 = std::ranges::min(points | std::views::transform(&Point::y));
assert(smallest_y2 == 0);
```

Let me place those two things together again to make this more clear:

```cpp
// this is the Point with the smallest Y coordinate
// because min(points, pred, proj) is always a Point
std::ranges::min(points, std::ranges::less{}, &Point::y)

// this is the smallest Y coordinate
// because we're starting from a range of Y coordinates
std::ranges::min(points | std::views::transform(&Point::y))
```

In both cases, we're using the same predicate (`std::ranges::less{}`, that's just the default argument to `ranges::min` so we didn't pass it in the second call. If we had named function arguments, we wouldn't have had to pass it in the first call either) and we're even using the same function to get the Y coordinate (`&Point::y`). It's just that in the first call, it is used to modify the predicate, whereas in the second call it is used to modify the range.

Going back to the original example that started this blog post, what the user wanted was to copy `std::string`s that met a certain criteria. In order to `ranges::copy_if` a bunch of `std::string`s, you need to have a range of `std::string`s. What the user wanted to do was this:

```cpp
std::ranges::copy_if(
        people | std::views::transform(&Person::last),
        std::back_inserter(r_names),
        [](std::string const& s) { return s[0] == 'R'; });
```

And by now it's hopefully clear why the original attempt was incorrect and why this one works.

### Preserving the Source Range

Another example might help demonstrate the difference between a projection (i.e. adapting the algorithm's predicate) and transformation (i.e. adapting the source range). Let's say we want to look in our `points` for a particular Y coordinate. There are potentially two ways to do that:

```cpp
// project into ranges::find
auto i = std::ranges::find(points, 5, &Point::y);

// transform points into a range of y-coordinates
auto j = std::ranges::find(points | std::views::transform(&Point::y), 5);
```

Which is preferred?

It helps to consider what `i` and `j` actually are. With `i`, we're `find`ing in `std::vector<Point>` so we get a `std::vector<Point>::iterator` back (note that it does not matter _what_ we're finding, only the source range). With `j`, we're `find`ing in a `std::ranges::transform_view<...>` so we get a `std::ranges::transform_view<...>::iterator` back out. With `i`, that's a useful result. With `j`, that is extremely unlikely to be useful -- what you need is `j.base()`.

Which might be a moot point anyway, since the `views::transform` version does not even compile to begin with because `points | std::views::transform(&Point::y)` is not a borrowed range.

The point here is: using projections allows you to preserve the source range, which means you get back iterators into the range that you want to get back iterators into. Transforming the source range is useful in other contexts, but these two approaches solve fundamentally different and orthogonal problems.

### Projections in the Standard Library

There are, broadly speaking, five kinds of projections used in the standard library (which is to say, in algorithms in the `std::ranges` namespace). Note that projections are always unary.

1. Applied to the argument of a unary function (e.g. `ranges::for_each`)
2. Applied to the argument of a unary predicate (e.g. `ranges::copy_if`)
3. Applied to both arguments of a binary predicate (e.g. `ranges::min`)
4. Two different projections, each applied to only one argument of a binary predicate (e.g. `ranges::equal`)
5. Applied to only one argument of a binary predicate (e.g. `ranges::lower_bound` and `ranges::upper_bound`)

I walked through some examples of the first three already (well, two of 'em anyway, there's not much difference between the unary function and unary predicate case). The [fourth](#rangesequal) and [fifth](#rangeslower_bound) kinds merit a description though. Indeed, `ranges::lower_bound` and `ranges::upper_bound` were _the_ motivations for adding projections, so I had better start with those.

Note that `ranges::find` technically doesn't fit any of those categories, but it's basically a special case of projecting one argument into a binary predicate (the predicate being `ranges::equal_to` and the other argument being the value that you're `find`ing).

#### `ranges::lower_bound`

In keeping with my `vector<Point> points` object from earlier, let's say I now what to start maintaining my points in sorted order, including subsequent inserts. But I don't want to sort it fully lexicographically, I just want to sort it by just the x-coordinate. And once I do that, I want to look for a particular x-coordinate using a binary search.

With the C++17 algorithms, that would look like:

```cpp
std::sort(points.begin(), points.end(), [](Point const& lhs, Point const& rhs){
    return lhs.x < rhs.x;
});
auto it = std::lower_bound(points.begin(), points.end(), x, [](Point const& p, int v){
    return p.x < y;
});
```

The binary predicate that `std::lower_bound` takes is heterogeneous, but the binary predicate that `std::sort` takes is homogeneous. And further, the binary predicate that `std::upper_bound` takes is also heterogeneous but with the reverse order of parameters. This is messy, can lead to surprises if your types happen to be cross-convertible, but more importantly means that you can't just use the same predicate in both contexts.

Projections address this problem. It's just that in `ranges::sort`, the projection is applied to both arguments, while in `ranges::lower_bound` (and `ranges::upper_bound`), the projection only has to be applied to the element from the range, not the value being looked for. This means that you don't have to remember which order the parameters go in (did I get them right earlier??), but importantly it means you can use the _same predicate_ and the _same projection_ for all of these algorithms.

The above, in C++20 using projections, is:

```cpp
std::ranges::sort(points, std::ranges::less{}, &Point::x);
auto it = std::ranges::lower_bound(points, x, std::ranges::less{}, &Point::x);
```

Or, since `std::ranges::less{}` is the default:

```cpp
std::ranges::sort(points, {}, &Point::x);
auto it = std::ranges::lower_bound(points, x, {}, &Point::x);
```

It may seem initially weird that we only apply the projection to half the arguments, and indeed this case doesn't map nicely onto `hof::proj`. We could write a `proj_left` and a `proj_right`. It's not that hard to do, but then we'd go back to having to remember which one of `proj_left` or `proj_right` you use for `ranges::lower_bound`. None of the other algorithms have this particular issue - projections are especially valuable in this case.

#### `ranges::equal`

Algorithms that take one range and a binary predicate really only need one projection, since all of your elements are only coming from one range. You just can't have more than one projection. But algorithms that take two ranges and a binary predicate could easily want to project each range separately and you need a way to do so.

For example, consider our `vector<Point> points` object from earlier. Let's say we wanted to compare its x-coordinates against a range of x-coordinates. We could still use `ranges::equal` for that, we just have to project the range of `Point` into a range of x-coordinate:

```cpp
std::vector<int> x_coords = {1, 1, 2, 3, 0, 6};

bool a = std::ranges::equal(points, x_coords, {}, &Point::x, {});
bool b = std::ranges::equal(x_coords, points, {}, {}, &Point::x);
assert(a and b);
```

Let me explain what's going on here. In both cases, I want to use `std::ranges::equal_to{}` as the binary predicate. But that's the default, so I can just write `{}`. Then, in the first call, I need to project only the left-hand range, while in the second call, I need to project only the right-hand range. The default projection is identity, so I can just write `{}` for the appropriate slot (and the trailing `{}` in the first call is unnecessary, I just added it so that the calls are clearly symmetric).

This is a great example for why named function arguments would be a great feature (and why strong typing is a non-solution), if I could just have written the above as:

```cpp
bool a = std::ranges::equal(points, x_coords, .by1 = &Point::x);
bool b = std::ranges::equal(x_coords, points, .by2 = &Point::x);
```

### In Summary

To conclude, and repeat: Projections do not change the algorithm. Projections are a simply convenient way to adapt the algorithm’s function or predicate. In most cases, this projection could be applied by the user directly using something like `hof::proj` (which should help make clear that projections simply adapt the function or predicate), but for `ranges::lower_bound` and `ranges::upper_bound`, the heterogeneous nature of the projection makes them especially valuable.
