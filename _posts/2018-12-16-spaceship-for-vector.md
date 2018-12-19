---
layout: post
title: "Implementing the spaceship operator for vector"
category: c++
series: operator<=>
tags:
 - c++
 - c++20
 - <=>
--- 

Last year, right after `operator<=>`{:.language-cpp} was added to the C++ working draft, I wrote a post about how to [implement `operator<=>`{:.language-cpp} for `optional<T>`{:.language-cpp}](https://medium.com/p/implementing-the-spaceship-operator-for-optional-4de89fc6d5ec). Long after I wrote that post, I ended up writing multiple papers to make changes to `operator<=>`{:.language-cpp} (see the [previous post]({% post_url 2018-11-12-improve-spaceship %}) in this series) and the original post is obsolete and needs to be revisited. While in that original post (and in [P1186R0](https://wg21.link/p1186r0)) I focused on `std::optional<T>`{:.language-cpp} and in the previous post I focused on `std::pair<T,U>`{:.language-cpp}, in this post I will instead focus on `std::vector<T>`{:.language-cpp}. The reasons for this (in addition to a general penchant for variety) are:

- For `vector<T>`{:.language-cpp}, unlike `pair<T,U>`{:.language-cpp}, the comparison operators cannot be defaulted. They are in that sense more interesting to consider.
- For `vector<T>`{:.language-cpp}, unlike `optional<T>`{:.language-cpp}, the relational operators are all defined in terms of `<`{:.language-cpp}. That is `p >= q`{:.language-cpp} is defined as `!(p < q)`{:.language-cpp}, so the type `T` only has to define `operator<`{:.language-cpp}. `optional<T>`{:.language-cpp} on the other hand is transparent, its `operator>=`{:.language-cpp} forwards to `T`'s `operator>=`{:.language-cpp}. The transformation done by `vector` is pretty typical for the standard library, and there is even blanket wording in the standard assuming this in [\[operators\]](http://eel.is/c++draft/operators) - but this transformation is only valid if the ordering defined by the type is a weak ordering. This fact will come into play later.

Ultimately, the reason I wanted to write this post right now isn't that I had an urge to implement more `operator<=>`{:.language-cpp}s. It's that with each discussion I have about this topic, I feel that I can do it better - and many of the arguments I've made in the past are just incorrect. Think of this post as my way of trying to figure out what the answer to these questions actually is.

## What do the comparison operators for `vector<T>`{:.language-cpp} look like today

Before I go in depth about how the comparison operators for `vector<T>`{:.language-cpp} could look tomorrow, I thought it would be helpful to start with how they look today:

```cpp
// just a convenience alias
template <typename T>
  using CREF = remove_reference_t<T> const&;

template <typename T>
  concept Cpp17EqualityComparable = requires(CREF<T> a, CREF<T> b) {
    { a == b } -> bool;
  };
    
template <typename T>
  concept Cpp17LessThanComparable = requires(CREF<T> a, CREF<T> b) {
    { a < b } -> bool;
  };
    
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

template <Cpp17EqualityComparable T>
bool operator!=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs == rhs);
}

template <Cpp17LessThanComparable T>
bool operator<(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare(lhs.begin(), lhs.end(),
                                   rhs.begin(), rhs.end());
}

template <Cpp17LessThanComparable T>
bool operator<=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs > rhs);
}

template <Cpp17LessThanComparable T>
bool operator>(vector<T> const& lhs, vector<T> const& rhs) {
    return rhs < lhs;
}

template <Cpp17LessThanComparable T>
bool operator>=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs < rhs);
}
```

We have 6 operators, 4 of which defer to one of the other 2. This is our starting point, and what we want to improve.

## Conditional `operator<=>`{:.language-cpp}

When it comes to adopting `operator<=>`{:.language-cpp} for library types, there are three choices a library can make:

1. Just don't adopt it.
2. Conditionally adopt it if all of its constituent types provide it.
3. Unconditionally adopt it, assuming the minimum semantics that the library requires.

There isn't much to say about option 1. This section will focus on option 2 - how to conditionally adopt the spaceship operator. This is the option that I've been the most wrong about in the past. 

To start with, regardless of which option we pick, two things hold:

1. We _must_ keep `operator==`{:.language-cpp} as is. It's not going anywhere and it's correct. After [P1185R0](https://wg21.link/p1185r0) (also described in the last post), it cannot be replaced with `operator<=>`{:.language-cpp}.
2. We can easily drop `operator!=`{:.language-cpp}. By default, `a != b`{:.language-cpp} will rewrite to `!(a == b)`{:.language-cpp} (technically to `(a == b) ? false : true`{:.language-cpp} to only require a contextual conversion to `bool`{:.language-cpp}). That is precisely what our operator does, so we don't need it. 

That drops us to 5 operators.

What I argued in P1186R0 was that conditionally adopting `operator<=>`{:.language-cpp} is bad because the way you would do that is:

```cpp
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const&, vector<T> const&);

// no operator!=

template <Cpp17LessThanComparable T>
bool operator<(vector<T> const&, vector<T> const&);

template <Cpp17LessThanComparable T>
bool operator<=(vector<T> const&, vector<T> const&);

template <Cpp17LessThanComparable T>
bool operator>(vector<T> const&, vector<T> const&);

template <Cpp17LessThanComparable T>
bool operator>=(vector<T> const&, vector<T> const&);

// these concepts courtesy of Casey Carter
template <typename T, typename Cat>
  concept compares-as = // exposition only
    Same<common_comparison_category_t<T, Cat>, Cat>;

template <typename T, typename Cat=std::partial_ordering>
  concept ThreeWayComparable = requires(CREF<T> a, CREF<T> b) {
    { a <=> b } -> compares-as<Cat>;
  };

template <typename T, typename U, typename Cat=std::partial_ordering>
  concept ThreeWayComparableWith = 
    ThreeWayComparable<T, Cat> && ThreeWayComparable<U, Cat> &&
    CommonReference<CREF<T>, CREF<U>> &&
    ThreeWayComparable<common_reference_t<CREF<T>, CREF<U>>, Cat> &&
    requires(CREF<T> t, CREF<U> u) {
      { t <=> u } -> compares-as<Cat>;
      { u <=> t } -> compares-as<Cat>;
    };

template <ThreeWayComparable T>
compare_3way_type_t<T> operator<=>(vector<T> const& lhs,
                                   vector<T> const& rhs) {
    return lexicographical_compare_3way(lhs.begin(), lhs.end(),
                                        rhs.begin(), rhs.end());
}
```

Any type which satisfies `ThreeWayComparable` would also satisfy `Cpp17LessThanComparable` (short of weird pathological cases where a type implements `operator<=>`{:.language-cpp} but deletes `operator<`{:.language-cpp}... don't do that), and the result would be that `p <=> q`{:.language-cpp} would invoke `operator<=>`{:.language-cpp} but `p < q`{:.language-cpp} would invoke `operator<`{:.language-cpp}. That's bad both because we would never actually invoke `<=>`{:.language-cpp} but also because `<=>`{:.language-cpp} could provide a faster ordering than `<`{:.language-cpp} could, and we're not taking advantage of this. 

But the above is not really an argument to avoid conditionally providing `operator<=>`{:.language-cpp}, it's simply an argument to avoid conditionally providing `operator<=>`{:.language-cpp} in this specific way. **Do not do this, I was wrong, it is wrong.**

In my [previous post]({% post_url 2018-11-12-improve-spaceship %}), I shows an improved implementation which gets you the right semantics you want: `p < q`{:.language-cpp} invokes `<=>`{:.language-cpp} if there is an `<=>`{:.language-cpp} that can be invoked. That implementation was a bit verbose, and actually could only be written using member functions. For `vector<T>`{:.language-cpp}, that would look like:

```cpp
template <typename T>
struct vector {
    bool operator==(vector<T> const&) const
        requires Cpp17EqualityComparable<T>;
    
    // the pre-existing operators
    bool operator< (vector<T> const&) const
        requires Cpp17LessThanComparable<T>;
    bool operator<=(vector<T> const&) const
        requires Cpp17LessThanComparable<T>;
    bool operator> (vector<T> const&) const
        requires Cpp17LessThanComparable<T>;
    bool operator>=(vector<T> const&) const
        requires Cpp17LessThanComparable<T>;
    
    // <=> and defaulted operators
    compare_3way_type_t<T> operator<=>(vector<T> const&) const
        requires ThreeWayComparable<T>;
    bool operator< (vector<T> const&) const
        requires Cpp17LessThanComparable<T> && ThreeWayComparable<T>
        = default;
    bool operator<=(vector<T> const&) const
        requires Cpp17LessThanComparable<T> && ThreeWayComparable<T>
        = default;
    bool operator> (vector<T> const&) const
        requires Cpp17LessThanComparable<T> && ThreeWayComparable<T>
        = default;
    bool operator>=(vector<T> const&) const
        requires Cpp17LessThanComparable<T> && ThreeWayComparable<T>
        = default;
};
```

The purposes of defaulting all those operators is to get around the problem in the previous implementation. Now, given `p < q`{:.language-cpp}, the defaulted candidate would be preferred to the pre-existing one (because of concepts and constraint subsumption). And `p < q`{:.language-cpp} for defaulted `<`{:.language-cpp} means exactly `(p <=> q) < 0`{:.language-cpp}. That was what we wanted to happen: for types which don't have spaceship yet, we preserve existing behavior, but for types which do have spaceship, we always invoke it. 

This solution is an improvement in semantics. But... we have to write 10 functions, 4 of which are defaulted? That's... not a good story.

It's here that Casey Carter provided me an improved solution to this problem that I'd never considered before. Instead of adding a new `operator<`{:.language-cpp} (and the rest) that are more constrained than the existing ones - we can actually change the constraints of the existing ones so they cease to be candidates in the presence of `<=>`{:.language-cpp}. This solution would not require any kind of defaulting, so we can go back to writing non-member functions.

That full solution, a `vector<T>`{:.language-cpp} which conditionally provides `<=>`{:.language-cpp} if and only if `T` does - but uses it for all the ordering comparisons, looks like this:

```cpp
template <typename T>
  concept OnlyLessThanComparable =
    Cpp17LessThanComparable<T> &&
    !ThreeWayComparable<T>;
    
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

// no operator!=

template <OnlyLessThanComparable T>
bool operator<(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare(lhs.begin(), lhs.end(),
                                   rhs.begin(), rhs.end());
}

template <OnlyLessThanComparable T>
bool operator<=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs > rhs);
}

template <OnlyLessThanComparable T>
bool operator>(vector<T> const& lhs, vector<T> const& rhs) {
    return rhs < lhs;
}

template <OnlyLessThanComparable T>
bool operator>=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs < rhs);
}

template <ThreeWayComparable T>
compare_3way_type_t<T> operator<=>(vector<T> const& lhs,
                                   vector<T> const& rhs) {
    return lexicographical_compare_3way(lhs.begin(), lhs.end(),
                                        rhs.begin(), rhs.end());
}
```

Now when we write `p < q`{:.language-cpp}, there will be exactly one candidate. If `T` is a legacy type that does not provide `operator<=>`{:.language-cpp}, the only candidate is `operator<`{:.language-cpp}. Otherwise, the only candidate will be a synthesized call to `operator<=>`{:.language-cpp} (because we disabled `operator<`{:.language-cpp}). 

I believe this is really the _correct way_ to conditionally provide `operator<=>`{:.language-cpp} for a library type. We still have to write 6 functions (not 10 as I'd previously claimed), we just swapped `operator!=`{:.language-cpp} for `operator<=>`{:.language-cpp}, but we have to be careful about how to properly constrain these operators. Negative concepts might be conceptually a little strange, but in this case they get the job done.

As you can hopefully see by my series of errors in attempting to solve this problem, it's decidedly non-trivial! Unlike my initial attempt in P1186, this solution is optimal. Unlike my second attempt last month, this solution doesn't require gratuitous defaulting of operators.

## Unconditional `operator<=>`{:.language-cpp}

The argument that I've made that does hold true is that providing conditional `operator<=>`{:.language-cpp} _is_ complicated. And it does require writing more code, where spaceship promised us that we could write less. But that's because we decided to write more code. We don't... _have_ to write more code. 

`std::vector<T>`{:.language-cpp}, like many types in the standard library, requires that its type provide a total ordering. Its current relational operators are written in terms of each other in a way that is not valid for partial orders, they are only valid for weak or strong orders. Taking those preexisting requirements to their logical conclusion, `vector`{:.language-cpp} could very well choose to synthesize an `operator<=>`{:.language-cpp} for `T` if `T` doesn't do so itself. Based on the idea of explicit defaulting first explored in the last post I keep citing, we could implement the full complement of comparisons for `vector<T>`{:.language-cpp} in terms of unconditional `operator<=>`{:.language-cpp} like so:

```cpp
// we're stuck with this one no matter what
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}


template <typename T>
struct with_fallback {
    CREF<T> val;
    
    // cat_with_fallback<T> is defined as
    // - decltype(t <=> t) if t <=> t is a valid expression
    // - else, weak_ordering if t < t is a valid expression with type bool
    // - else, void
    cat_with_fallback<T> operator<=>(with_fallback const&) const = default;
};

template <typename T, ThreeWayComparable WF = with_fallback<T>>
compare_3way_type_t<WF> operator<=>(vector<T> const& lhs,
                                    vector<T> const& rhs)
{
    return lexicographical_compare_3way(
        lhs.begin(), lhs.end(), rhs.begin(), rhs.end(),
        [](T const& lhs, T const& rhs){
            return WF{lhs} <=> WF{rhs};
        });
}
```

This bears some further explaining. The explicit defaulting is a new language proposal that I haven't written yet, but the idea is that if `T` provides an `operator<=>`{:.language-cpp}, `with_fallback`'s spaceship just transparently invokes it. But if `T` does not yet provide an `operator<=>`{:.language-cpp}, but does provide an `operator<`{:.language-cpp}, we will assume that that operator defines a weak ordering, and synthesize an `operator<=>`{:.language-cpp} that is solely based on `<`{:.language-cpp}:

```cpp
weak_ordering __synthesized_operator<=>(with_fallback const& rhs) const {
    if (val < rhs.val) return weak_ordering::less;
    if (rhs.val < val) return weak_ordering::greater;
    return weak_ordering::equivalent;
}
```

If `T` doesn't provide either of the two operators, then `with_fallback`'s `operator<=>`{:.language-cpp} will be defined as deleted. As a result, `with_fallback<T>`{:.language-cpp} would not satisfy `ThreeWayComparable` and the entire operator would be removed from the overload set.

We assume `weak_ordering` and not `partial_ordering` because that is what the standard library typically assumes. But if we try to use a `T` that provides an `operator<=>`{:.language-cpp} that returns `partial_ordering`, then `vector<T>`{:.language-cpp} will use that, and it will work correctly. That is, comparing `vector<float>`{:.language-cpp}s would work correctly - such a comparison is a `partial_ordering`. Comparing `vector<int>`{:.language-cpp}s would be a `strong_ordering`. 

Is this approach to providing an unconditional `operator<=>`{:.language-cpp} for `vector<T>`{:.language-cpp} more complex than the previously demonstrating approach of providing a conditional `operator<=>`{:.language-cpp}? You only have to implement two functions instead of six. It is easier to properly constrain those two functions than it is to properly constrain the previous six.

The complexity here is localized in determining _what_ the fallback category should be and _how_ to synthesize `<=>`{:.language-cpp} for it.

## Synthetic `operator<=>`{:.language-cpp}

It turns out, there are multiple ways to synthesize `operator<=>`{:.language-cpp} from other operators based on the selected return type, at least for the weaker ordering categories. And additionally, we could throw in some sanity checking to ensure that our total orderings really are total orderings.

For example, `strong_ordering` is the most straightforward - it can really only go one way:

```cpp
template <typename T>
strong_ordering __synthesized_operator<=>(T const& x, T const& y) {
    if (x == y) return strong_ordering::equal;
    if (x < y)  return strong_ordering::less;
    [[assert: x > y]];
    return x > y;
}
```

That assertion had better hold - otherwise we don't really have a strong ordering, we necessarily have a partial one!