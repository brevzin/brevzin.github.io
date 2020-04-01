---
layout: post
title: "Implementing span's comparisons"
category: c++
tags:
  - c++
  - c++20
  - span
  - <=>
---

One of the new types in C++20 is `std::span<T>`{:.language-cpp} (with its fixed-
size counterpart `std::span<T, N>`{:.language-cpp}). This is a very useful type,
since it's a type-erased view onto a contiguous range - but unlike more typical
type erasure (e.g. `std::function`{:.language-cpp}), there's no overhead. I've
previous written about `span` [here]({% post_url 2018-12-03-span-best-span %}).

In the initial design, `std::span<T>`{:.language-cpp} had comparison operators
that performed a _deep comparison_. Those operators were subsequently removed.
I think that removal was a mistake, since these operators are very useful (as in,
we have a `span`-like type in our codebase and we use these operators), but this
blog isn't going to be about why they were removed or why they should be added
back.

Instead, this blog is about _how_ to implement span's comparison operators, since
I think that is interesting and demonstrates a bunch of C++20 features all in
one go. You can jump straight to the C++20 implementation [here](#cpp20) or you
can just directly add it to your code base using my `span_ext` repo
[here](https://github.com/BRevzin/span_ext).

### Design

Let's start with a quick design. Before we start implementing comparisons, we have
to decide what we're going to allow comparing to. Here are six types that a
`std::span<int>`{:.language-cpp} could hypothetically be comparable with:

{:start="0"}
0. `std::span<int>`{:.language-cpp}
1. `std::span<int const>`{:.language-cpp}
2. `std::span<long>`{:.language-cpp}
3. `std::vector<int>`{:.language-cpp}
4. `std::list<int>`{:.language-cpp}
5. `std::vector<long>`{:.language-cpp}

I started with `span<int>`{:.language-cpp} as zero because that goes without
saying. `span<int const>`{:.language-cpp} should also work, since `const`{:.language-cpp}-ness
should not play in comparisons.

For the rest, I would argue that `std::vector<int>`{:.language-cpp} should be
comparable but neither `std::list<int>`{:.language-cpp} nor `std::vector<long>`{:.language-cpp}
nor `std::span<long>`{:.language-cpp}
should be. My position is that span's comparisons should behave like a glorified
`memcmp` - and it should only be directly comparable with other contiguous ranges
of the same type.

That is, the nice syntax (`==`{:.language-cpp}) only is allowed for the direct,
likely-to-be-valid comparisons. For everything else, if you really want to
compare a `std::span<int>`{:.language-cpp} to a `std::list<long>`{:.language-cpp},
you can use `std::ranges::equal`{:.language-cpp}.

This is actually different from the [span paper](https://wg21.link/p0122), where
the defined comparisons where that `std::span<T>`{:.language-cpp} was only
comparable to `std::span<U>`{:.language-cpp}. But, in my opinion, it makes a lot
more sense to compare a `std::span<int>`{:.language-cpp} to a
`std::vector<int>`{:.language-cpp} than to a `std::span<long>`{:.language-cpp}.
While mixed-category comparisons can [get you in trouble]({% post_url 2018-12-09-mixed-comparisons %}), here they're not _really_ different categories -
and this lets us write `s == v`{:.language-cpp} instead of
`s == std::span(v)`{:.language-cpp} (using CTAD, and note that this conversion
is basically free compared to the comparison).

### Implementation in C++17

Given that design, how would we go about implementing it? (If you want, you can
skip to the [C++20 implementation](#cpp20)).

We want to allow cross-type comparisons, and we want to of course allow them
in both directions. We don't want to be in a position where `s == v`{:.language-cpp}
compiles but `v == s`{:.language-cpp} does not compile or, worse, compiles
and does something different.

Ignoring constraints for now, that means we're starting with (also I'm
omiting `constexpr`{:.language-cpp} for slide-ware):

```cpp
namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span { /* ... */ };

  template <typename T, size_t Extent, typename R>
  bool operator==(span<T, Extent> lhs,
                            R const& rhs) {
    // we don't have to bring in namespace std here since
    // we're already in namespace std. But qualified call
    // to std::equal to avoid ADL shenanigans
    return std::equal(begin(lhs), end(lhs),
        begin(rhs), end(rhs));
  }

  template <typename T, size_t Extent, typename R>
  bool operator==(R const& lhs,
                            span<T, Extent> rhs) {
    return rhs == lhs;
  }
  
  // and != overloads that just call ==
  template <typename T, size_t Extent, typename R>
  bool operator!=(span<T, Extent> lhs, R const& rhs) {
    return !(lhs == rhs);
  }

  template <typename T, size_t Extent, typename R>
  bool operator!=(R const& lhs, span<T, Extent> rhs) {
    return !(rhs == lhs);
  }
  
  // ... and <, <=, >, >=
}
```

The actual implementation for a specific comparison operator is trivial - we
have algorithms for those. Think about how you would implement `operator<`{:.language-cpp}.

This puts us at 12 operators. Tedious, and we're missing constraints (that would
need to be duplicated everywhere), but are we done? What happens when I just
write:

```cpp
std::span<int> x = /* ... */;
std::span<int> y = /* ... */;
bool check = (x == y);
```

This is the simplest case, right? Just same-type comparison. Here's the
error message we get from gcc trunk:

```
<source>:18:17: error: ambiguous overload for 'operator==' (operand types are 'std::span<int>' and 'std::span<int>')
   18 | bool check = (x == y);
      |               ~ ^~ ~
      |               |    |
      |               |    span<[...]>
      |               span<[...]>
<source>:10:20: note: candidate: 'bool std::operator==(std::span<T, Extent>, const R&) [with T = int; long unsigned int Extent = 18446744073709551615; R = std::span<int>]'
   10 |     bool operator==(span<T, Extent> lhs, R const& rhs);
      |          ^~~~~~~~
<source>:13:20: note: candidate: 'bool std::operator==(const R&, std::span<T, Extent>) [with T = int; long unsigned int Extent = 18446744073709551615; R = std::span<int>]'
   13 |     bool operator==(R const& rhs, span<T, Extent> lhs);
      |          ^~~~~~~~
```

That is a great error message. The problem is - we have two `operator==`{:.language-cpp}
candidates. One is a template on the left argument and one is a template on the
right argument, both are viable, and neither is any more specialized than the other.

How do we fix this?

One way to fix this is to just... add more overloads! Add a third candidate for
`operator==`{:.language-cpp} that is just comparison two spans:

```cpp
namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span { /* ... */ };

  template <typename T, size_t Extent, typename R>
  bool operator==(span<T, Extent> lhs, R const& rhs);

  template <typename T, size_t Extent, typename R>
  bool operator==(R const& lhs, span<T, Extent> rhs);
  
  template <typename T, size_t E1, size_t E2>
  bool operator==(span<T, E1>, span<T, E2>);
}
```

Here, the _extents_ can be different but the types must be the same. And this
works. Indeed, by design, since we're only comparing contiguous things, we can
even funnel both generic range comparison operators to the span specific one,
so that a solution of `operator==`{:.language-cpp} (with proper constraints)
could be:

```cpp
#define REQUIRES(...) std::enable_if_t<\
    (__VA_ARGS__), int> = 0

// check if we can compare two Ts
template <typename T>
inline constexpr bool equality_comparable_v =
    std::is_invocable_v<std::equal_to<>,
        T const&, T const&> &&
    std::is_invocable_v<std::not_equal_to<>,
        T const&, T const&>;

namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span { /* ... */ };

  template <typename T, size_t E1, size_t E2,
    REQUIRES(equality_comparable_v<T>)>
  bool operator==(span<T, E1> lhs, span<T, E2> rhs) {
    // could even check if E1/E2 are different
    // fixed extents, return false
    return std::equal(
        lhs.begin(), lhs.end(),
        rhs.begin(), rhs.end());
  }
  
  template <typename T, size_t E, typename R,
    REQUIRES(equality_comparable_v<T> &&
             std::is_constructible_v<span<T>, R const&>)>
  bool operator==(span<T, E> lhs, R const& rhs) {
    return lhs == std::span<T>(rhs);
  }
  
  template <typename T, size_t E, typename R,
    REQUIRES(equality_comparable_v<T> &&
             std::is_constructible_v<span<T>, R const&>)>
  bool operator==(R const& lhs, span<T, E> rhs) {
    return rhs == std::span<T>(lhs);
  }
}
```

This solves the comparison problem we had earlier. Now all we need to do is
repeat this for every other comparison operator, for a grand total of... 18.
18 comparison operators! Of which, two actually do work and the other 16 just forward onto
those two. Cool? Seems unsatisfying.

Also, does this even work?

Actually, no. While this lets me compare a `span<int>`{:.language-cpp} to a
`span<int>`{:.language-cpp}, which would be the bare minimum requirement anyway,
it doesn't even let me compare a `span<int>`{:.language-cpp} to a
`span<int const>`{:.language-cpp}. Nor actually, with the constraints I added
above, does it let me compare a `span<int>`{:.language-cpp} to a `vector<int>`{:.language-cpp}
because `span<int>`{:.language-cpp} is not constructible from a
`vector<int> const&`{:.language-cpp}!

Both of those are fixable by introducing the new constraint `sameish`: two types
are the _sameish_ if they're the same after removing `const`{:.language-cpp}-ness
(`int`{:.language-cpp} and `int const`{:.language-cpp} aren't the same - but they're
the same...ish).

```cpp
#define REQUIRES(...) std::enable_if_t<\
    (__VA_ARGS__), int> = 0

// check if we can compare two Ts
template <typename T>
inline constexpr bool equality_comparable_v =
    std::is_invocable_v<std::equal_to<>,
        T const&, T const&> &&
    std::is_invocable_v<std::not_equal_to<>,
        T const&, T const&>;

template <typename T, typename U>
inline constexpr bool sameish =
    std::is_same_v<std::remove_cv_t<T>,
                   std::remove_cv_t<U>>;

namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span { /* ... */ };

  template <typename T, size_t E1, typename U, size_t E2,
    REQUIRES(sameish<T, U> && equality_comparable_v<T>)>
  bool operator==(span<T, E1> lhs, span<U, E2> rhs) {
    return std::equal(
        lhs.begin(), lhs.end(),
        rhs.begin(), rhs.end());
  }
  
  template <typename T, size_t E, typename R,
    REQUIRES(equality_comparable_v<T> &&
             std::is_constructible_v<span<T const>,
                                     R const&>)>
  bool operator==(span<T, E> lhs, R const& rhs) {
    return lhs == std::span<T const>(rhs);
  }
  
  template <typename T, size_t E, typename R,
    REQUIRES(equality_comparable_v<T> &&
             std::is_constructible_v<span<T const>,
                                     R const&>)>
  bool operator==(R const& lhs, span<T, E> rhs) {
    return rhs == std::span<T const>(lhs);
  }
}
```

This, finally, is a complete solution. Well, it would be nice if we checked
not only that `T == T`{:.language-cpp} is a valid expression but also that it
was convertible to `bool`{:.language-cpp}, so it's _nearly_ complete. But it
does satisfy the rest of the requirements I set out earlier... at the cost of
having to write 18 operators and some very careful constraints.

Moreover, you really have to test those 18 operators carefully - while writing
this blog I made numerous typos in these implementations (and no promises that
I fixed all of them either), which would only be caught in testing... 


### Implementation in C++17 with hidden friends

But wait, there's this technique that people like to use to implement comparison
operators called _hidden friends_. Does that help us here?

```cpp
namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span {
    // ...
    
    template <typename U=T,
      REQUIRES(equality_comparable_v<U>)>
    friend bool operator==(span lhs, span rhs);
  };
```

And the answer is... not really, no. If I have a `vector<int> const`{:.language-cpp},
I'm simply not going to be able to compare it to a `span<int>`{:.language-cpp}
in this way. 

If I make the hidden friend take two `span<T const>`{:.language-cpp} objects
instead, then I have to deal with redefinition issues with `span<T>`{:.language-cpp}
and `span<T const>`{:.language-cpp} competing to define the same operators.

I don't think there's a solution here. At least, I can't think of one.

### Implementation in C++20 {#cpp20}

Thankfully, C++20 is here and we can do... so much better. With the combination
of three large features:

- Concepts
- Ranges
- `operator<=>`{:.language-cpp} (or generally, C++20 comparisons)

Our initial design was that `span<T>`{:.language-cpp} should be comparable to
any contiguous range of the _sameish_ type, as long a that type is appropriately
comparable.

Since we're going to need that particular constraint in multiple places, let's
turn it into a proper concept:

```cpp
// a contiguous range whose value type and T
// are the sameish type
// (range_value_t shouldn't be cv-qualified)
template <typename R, typename T>
concept const_contiguous_range_of =
    contiguous_range<R const> &&
    std::same_as<
        std::remove_cvref_t<T>,
        std::ranges::range_value_t<R const>>;
```

And now we can directly translate our requirements into code:

```cpp
namespace std {
  template <typename T, size_t Extent=dynamic_extent>
  class span { /* ... */ };
  
  template <equality_comparable T, size_t E, 
            const_contiguous_range_of<T> R>
  bool operator==(span<T, E> lhs, R const& rhs)
  {
    return ranges::equal(lhs, rhs);
  }
  
  template <three_way_comparable T, size_t E,
            const_contiguous_range_of<T> R>
  auto operator<=>(span<T, E> lhs, R const& rhs)
  {
    return std::lexicographical_compare_three_way(
        lhs.begin(), lhs.end(),
        ranges::begin(rhs), ranges::end(rhs));
  }
}
```

That's it. That's... the complete solution. Just two operators, with constraints
that are quite straightforward to write, both of whose implementations are roughly
trivial (now, if you want to support types that do not provide `<=>`{:.language-cpp},
you'll have to use <i>`synth-three-way`</i> in [\[expos.only.func\]](http://eel.is/c++draft/expos.only.func) and constrain based on that). Moreover,
unlike before, these can (and probably should) be member function templates. The
only reason I'm making them non-member function templates is that it's the only
way I can add them outside of the standard library.

Why do we only need 2 operators where previously we needed 18? Because C++20's
comparison operators allow reversed and synthesized comparisons. Let's go through
a few examples to see what the candidate sets are and how overload resolution
actually works. See also [Comparisons in C++20]({% post_url 2019-07-28-comparisons-cpp20 %})
for a more thorough treatment.

#### Comparing `span<int>`{:.language-cpp} to `span<int>`{:.language-cpp} with `==`{:.language-cpp}

We'll have two candidates (I'm going to ignore extents for simplicity):

1. `operator==(span<T>, R const&)`{:.language-cpp} with `T=int`{:.language-cpp}
and `R=span<int>`{:.language-cpp}.
2. `operator==(R const&, span<T>)`{:.language-cpp} with `T=int`{:.language-cpp}
and `R=span<int>`{:.language-cpp}. This is the reversed candidate.

Both are exact matches (no conversions in either argument), neither function template
is more specialized than the other, neither is more constrained than the other.
But we prefer the non-reversed candidate to the reversed one, so this works and
is unambiguous (and the implementation is hopefully obviously correct).

#### Comparing `span<int>`{:.language-cpp} to `span<int const>`{:.language-cpp} with `==`{:.language-cpp}

We again have two candidates, though they of course deduce differently:

1. `operator==(span<T>, R const&)`{:.language-cpp} with `T=int`{:.language-cpp}
and `R=span<int const>`{:.language-cpp}.
2. `operator==(R const&, span<T>)`{:.language-cpp} with `T=int const`{:.language-cpp}
and `R=span<int>`{:.language-cpp}

The difference in deduction doesn't really matter though - both candidates are
exact matches, with neither function template more specialized or more constrained
than the other, so we prefer the non-reversed candidate. This works and is
unambiguous.

#### Comparing `span<int>`{:.language-cpp} to `span<int>`{:.language-cpp} with `!=`{:.language-cpp}

Since there is no `operator!=`{:.language-cpp} candidate, this works exactly the
same way as `==`{:.language-cpp} does, except in the end
instead of evaluating `x == y`{:.language-cpp} we evaluate
`!(x == y)`{:.language-cpp}.

Since `x != y`{:.language-cpp} nearly always means `!(x == y)`{:.language-cpp},
we get it for free alongside `x == y`{:.language-cpp}.

#### Comparing `vector<int>`{:.language-cpp} to `span<int>`{:.language-cpp} with `==`{:.language-cpp}

This time, the normal operator isn't a candidate (since `vector<int>`{:.language-cpp}
is not any kind of `span<T>`{:.language-cpp}) but the reversed operator is: we
still deduce `R=vector<int>`{:.language-cpp} and `T=int`{:.language-cpp}. That's
our only candidate, it's viable, and it works.

#### Comparing `span<int>`{:.language-cpp} to `list<int>`{:.language-cpp} with `==`{:.language-cpp}

Similar to the above, only the normal candidate would be potentially viable -
but after we deduce `R=list<int>`{:.language-cpp}, we see that `R` fails to
satisfy the constraint that it is a contiguous range. The normal candidate is
removed from consideration, and we end up with no viable candidates.

#### Comparing `span<int>`{:.language-cpp} to `vector<long>`{:.language-cpp} with `==`{:.language-cpp}

As above, only the normal candidate would be potentially viable, and here
`R=vector<long>`{:.language-cpp} is actually a contiguous range. But that's not
our only constraint, we also require the _sameish_ value type - and `int`{:.language-cpp}
and `long`{:.language-cpp} are not sameish. Hence, we again end up with no
viable candidates.

#### Comparing `vector<int>`{:.language-cpp} to `span<int>`{:.language-cpp} with `<`{:.language-cpp}

Enough about `==`{:.language-cpp}, here's an example with `<`{:.language-cpp}.

We don't have any `operator<`{:.language-cpp} candidates, but we do
have an `operator<=>`{:.language-cpp} candidate with its parameters reversed.
This deduces `R=vector<int>`{:.language-cpp} and `T=int`{:.language-cpp}, all
the constraints are satisfied. It's the only candidate, and it's viable.

This gets applied to our code that did `v < s`{:.language-cpp} and rewrites it
to evaluate as `0 < operator<=>(s, v)`{:.language-cpp} (note the reversal of 
arguments into the function). Had we compared in the other direction,
`s < v`{:.language-cpp} would rewrite to `operator<=>(s, v) < 0`{:.language-cpp}.

### Try It Out

As you can see, implementing `span`'s comparison operators in C++20 is remarkably
easy comparing to what this was like in C++17. I wouldn't call the implementation
_trivial_ - it still took thought to come up with the correct constraints - though
it does seem trivial in comparison.

Even though `std` won't provide these comparison operators, and it's somewhat
naughty to do so externally, I created a repo that does exactly this:
[span_ext](https://github.com/BRevzin/span_ext). It's a single header that
implements all of the comparison operators for `std::span`{:.language-cpp} in
C++20. It's built on top of concepts, ranges, and `<=>`{:.language-cpp} like
I showed in this blog. I'm not the best at CMake, patches welcome!

But libc++ does not have the C++20 library functionality yet, so it instead
can use range-v3 for all the relevant pieces. That's why the header is, at the
time of this writing anyway, 162 lines of code instead of like 20 - because most
of it implementing other C++20 library things that may not necessarily exist yet.

C++20 may lack comparisons for `std::span`{:.language-cpp}, but it's still going
to be great.
