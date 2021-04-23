---
layout: post
title: "Conditionally implementing spaceship"
category: c++
series: operator<=>
tags:
 - c++
 - c++20
 - <=>
--- 

When it comes to adopting `operator<=>`{:.language-cpp} for library class templates, there are three choices a library  can make:

1. Just don't adopt it (Never Spaceship)
2. Conditionally adopt it if all of its constituent types provide it (Sometimes Spaceship)
3. Unconditionally adopt it, if necessary assuming the minimum semantics that the library requires (Always Spaceship)

There isn't really that much to say about Never Spaceship. This post will focus on Sometimes Spaceship - how to conditionally provide spaceship. Always Spaceship will be the subject of a future post (I'm using "Always" here to still be conditioned on the type having comparison operators - I'm not suggesting that you take a type without any comparisons defined, stick it in a `vector` and suddenly you can compare them).

In [P1186R0](https://wg21.link/p1186r0), I focused on `std::optional<T>`{:.language-cpp} and in the [previous post]({% post_url 2018-11-12-improve-spaceship %}) in this series, I talked about `std::pair<T, U>`{:.language-cpp}. In this post I will instead focus on `std::vector<T>`{:.language-cpp}. The reasons for this (in addition to a general penchant for variety) are:

- For `vector<T>`{:.language-cpp}, unlike `pair<T,U>`{:.language-cpp}, the comparison operators cannot be defaulted. They are, in that sense, more interesting to consider.
- For `vector<T>`{:.language-cpp}, unlike `optional<T>`{:.language-cpp}, the relational operators are all defined in terms of `<`{:.language-cpp}. That is `p >= q`{:.language-cpp} is defined as `!(p < q)`{:.language-cpp}, so the type `T` only has to define `operator<`{:.language-cpp}. `optional<T>`{:.language-cpp} on the other hand is transparent, its `operator>=`{:.language-cpp} forwards to `T`'s `operator>=`{:.language-cpp}. The transformation done by `vector` is pretty typical for the standard library, and there is even blanket wording in the standard assuming this in [\[operators\]](http://eel.is/c++draft/operators). I'll explain the significance of this in the future Always Spaceship post.

Ultimately, the reason I wanted to write this post right now isn't that I had an urge to implement more `operator<=>`{:.language-cpp}s. It's that with each discussion I have about this topic, I feel that I can do it better - and many of the arguments I've made in the past are just incorrect and my previous attempts at solving this problem need to be improved. Think of this post as my way of trying to figure out how to actually solve this problem.

## C++17 status quo for `vector<T>`{:.language-cpp}

Before I go in depth about how the comparison operators for `vector<T>`{:.language-cpp} could look tomorrow, I thought it would be helpful to start with how they look today. I'm going to use concepts anyway, just for convenience. We've had concepts in the standard for quite some time - just not as a language feature - so this isn't too much of a stretch (although for `vector<T>`{:.language-cpp}, none of these operators are actually constrained according to the standard).

```cpp
// just a convenience alias
template <typename T>
using CREF = remove_reference_t<T> const&;

// the "concepts" for comparisons as they exist in the Standard
// Library today. I am just using them for convenience
template <typename T>
concept Cpp17EqualityComparable = requires(CREF<T> a, CREF<T> b) {
  { a == b } -> convertible_to<bool>;
};
    
template <typename T>
concept Cpp17LessThanComparable = requires(CREF<T> a, CREF<T> b) {
  { a < b } -> convertible_to<bool>;
};
    
// two operators actually implement functionality
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

template <Cpp17LessThanComparable T>
bool operator<(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare(lhs.begin(), lhs.end(),
                                   rhs.begin(), rhs.end());
}

// the other four just forward to one of the first two
template <Cpp17EqualityComparable T>
bool operator!=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs == rhs);
}

template <Cpp17LessThanComparable T>
bool operator<=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(rhs < lhs);
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

## A `concept`{:.language-cpp} for `operator<=>`{:.language-cpp}

Before I get into any further implementation, we need a `concept`{:.language-cpp} for the spaceship operator. With a lot of help from Casey Carter, this is what I'm gong to propose for C++20:

```cpp
template <typename T, typename Cat>
  concept compares-as = // exposition only
    Same<common_comparison_category_t<T, Cat>, Cat>;

template <typename T, typename Cat=std::partial_ordering>
  concept ThreeWayComparable = requires(CREF<T> a, CREF<T> b) {
    { a <=> b } -> compares-as<Cat>;
  };

template <typename T, typename U,
          typename Cat=std::partial_ordering>
  concept ThreeWayComparableWith = 
    ThreeWayComparable<T, Cat> &&
    ThreeWayComparable<U, Cat> &&
    CommonReference<CREF<T>, CREF<U>> &&
    ThreeWayComparable<
      common_reference_t<CREF<T>, CREF<U>>,
      Cat> &&
    requires(CREF<T> t, CREF<U> u) {
      { t <=> u } -> compares-as<Cat>;
      { u <=> t } -> compares-as<Cat>;
    };
```

If we just wrote the requirement as `{ t <=> u } -> convertible_to<Cat>`{:.language-cpp}, that would allow for some awkward things like returning a type that isn't a comparison category but happens to have a conversion operator for one. I don't know that anybody would ever actually _write_ that, but it's better to just be more explicit. What we want to say isn't that the type is _convertible_ to `Cat`, we want to say that it's _specifically_ a comparison category that is convertible to `Cat`. That's what `common_comparison_category_t<T, Cat>`{:.language-cpp} is for - that type will either be `void`{:.language-cpp} (if either type isn't actually a comparison category) or the weaker of `T` and `Cat` - we're okay with `Cat` being weaker than `T`, but not vice versa. Hence the `Same`.

The heterogeneous comparison concept follows the pattern of the other standard library concepts. We're not just checking syntax, we're checking full semantics. It's not just that syntactically you can write `t <=> u`{:.language-cpp}, it's that all variations of that make sense, including `t <=> t`{:.language-cpp} and `u <=> u`{:.language-cpp}.

## Conditionally adopting `operator<=>`{:.language-cpp}, Take 1

To start with, we _must_ keep `operator==`{:.language-cpp} as is. It's not going anywhere and it's correct. After [P1185R0](https://wg21.link/p1185r0) (also described in the last post), it cannot be replaced with `operator<=>`{:.language-cpp}. Even if we choose to unconditionally provide `<=>`{:.language-cpp}, we need still to provide `operator==`{:.language-cpp} too. `a == b`{:.language-cpp} never calls `a <=> b`{:.language-cpp} implicitly.

But we can easily drop `operator!=`{:.language-cpp}. By default, `a != b`{:.language-cpp} will rewrite to `!(a == b)`{:.language-cpp} (technically to `(a == b) ? false : true`{:.language-cpp} to sidestep the language having to deal with `operator!()`{:.language-cpp} and only require a contextual conversion to `bool`{:.language-cpp} - I preferred to write the conditional operator than `!static_cast<bool>(a == b)`{:.language-cpp}...). That is precisely what our operator does, and that is precisely what all `operator!=`{:.language-cpp}s should do, so we don't need it to write it. Ever again.

That drops us to 5 operators.

What I argued in P1186R0 was that conditionally adopting `operator<=>`{:.language-cpp} is bad because the way you would do that is:

```cpp
// same two operators providing functionality
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

template <Cpp17LessThanComparable T>
bool operator<(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare(lhs.begin(), lhs.end(),
                                   rhs.begin(), rhs.end());
}

// just three other "forwarding" operators
template <Cpp17LessThanComparable T>
bool operator<=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(rhs < lhs);
}

template <Cpp17LessThanComparable T>
bool operator>(vector<T> const& lhs, vector<T> const& rhs) {
    return rhs < lhs;
}

template <Cpp17LessThanComparable T>
bool operator>=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs < rhs);
}

// and Sometimes Spaceship
template <ThreeWayComparable T>
compare_3way_type_t<T> operator<=>(vector<T> const& lhs,
                                   vector<T> const& rhs) {
    return lexicographical_compare_3way(lhs.begin(), lhs.end(),
                                        rhs.begin(), rhs.end());
}
```

Any type which satisfies `ThreeWayComparable` would also satisfy `Cpp17LessThanComparable` (short of weird pathological cases where a type implements `operator<=>`{:.language-cpp} but deletes `operator<`{:.language-cpp}... don't do that), and the result would be that `p <=> q`{:.language-cpp} would invoke `operator<=>`{:.language-cpp} but `p < q`{:.language-cpp} would invoke `operator<`{:.language-cpp}. That's bad both because we would never actually invoke `<=>`{:.language-cpp} (which would become oddly useless) but also because `<=>`{:.language-cpp} could provide a faster ordering than `<`{:.language-cpp} could, and we're not taking advantage of this (for `vector<T>`{:.language-cpp}, we'd be making up to `2N-1`{:.language-cpp} calls to `<`{:.language-cpp} when we could be making just `N`{:.language-cpp} calls to `<=>`{:.language-cpp}). 

That's the argument I made in P1186 - and the above paragraph is totally true and I stand by it. But it's not really an argument against Sometimes Spaceship, it's simply an argument to avoid _this specific implementation strategy_ for Sometimes Spaceship.

**Do not do this, I was wrong, it is wrong. This is an anti-pattern.**

## Conditionally adopting `operator<=>`{:.language-cpp}, Take 2

In my [previous post]({% post_url 2018-11-12-improve-spaceship %}), I shows an improved implementation which gets you the right semantics you want: `p < q`{:.language-cpp} invokes `<=>`{:.language-cpp} if there is an `<=>`{:.language-cpp} that can be invoked, and only invokes `<`{:.language-cpp} if there is no spaceship candidate. That implementation was a bit verbose, and actually could only be written using member functions. For `vector<T>`{:.language-cpp}, that would look like:

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

This solution is an improvement in semantics. But... we have to write 10 functions, 4 of which are defaulted? That's... not a good story. Plus we're stuck writing these as member functions, and member functions have slightly different semantics than non-member functions. It'd be good to pick your implementation strategy based on the semantics you want for those comparisons - not just as a result of only having a single option.

## Conditionally adopting `operator<=>`{:.language-cpp}, Take 3

Let's take a step back and reconsider what is actually going on here, and what we are trying to accomplish (and a big thank you to Casey Carter for spending the time to help me improve this solution and to give me the tools to come up with a better one). 

Typically, when we perform overload resolution, we look up a particular name (like `begin` or `operator<<`{:.language-cpp}), find all the candidates with that name, and then pick the best one. Importantly, the candidates that we look up all are named the same. We pick the best `begin`, or the best `operator<<`{:.language-cpp}, etc. It's tempting to extend this intuition out to understanding spaceship - and think that the way overload resolution continues to work with an expression like `p < q`{:.language-cpp} is that we pick the best `operator<`{:.language-cpp} among the `operator<`{:.language-cpp}s and, if we can't find one, fallback to looking up `p <=> q < 0`{:.language-cpp}. 

But that isn't how it works at all. We do something fairly novel - our candidate set for relational comparisons includes **both** `operator<`{:.language-cpp} candidates **and** `operator<=>`{:.language-cpp} candidates **and** reversed `operator<=>`{:.language-cpp} candidates. We try to pick the best viable candidate amongst this entire set. The relevant order of tie-breakers here is (filtered from [\[over.match.best\]](http://eel.is/c++draft/over.match.best)):

1. Better conversion sequence
2. Prefer the candidate that is NOT a function template specialization to one that is
3. Prefer the more specialized function template (partial ordering rules)
4. Prefer the more constrained function template (concept subsumption rules)
5. Prefer the non-rewritten candidate (i.e. in this case `p < q`{:.language-cpp}, prefer an `operator<`{:.language-cpp} to an `operator<=>`{:.language-cpp})
6. Prefer the non-reversed candidate (i.e. in this case `p < q`{:.language-cpp}, prefer `p <=> q < 0`{:.language-cpp} to `0 < (q <=> p)`{:.language-cpp})

What in here can we use to our advantage? To restate our goal: we want `p < q`{:.language-cpp} to invoke `operator<=>`{:.language-cpp} if that is a viable candidate, otherwise to fall-back to `operator<`{:.language-cpp} if that is a viable candidate.

If we look at our operator declarations, #1, #2, and #3 will just never apply. Every operator takes both of its arguments as `vector<T> const&`{:.language-cpp}. Same conversion sequences, everything is a template, nothing is more specialized. The next tie-breaker is #4. Can we take advantage of that one? Yes, we can! We just have to make spaceship _more constrained_ than each of the relational operators. That's just a matter of ensuring that subsumption happens.

The pattern we want is this:

```cpp
template <Cpp17LessThanComparable T>
bool operator<(T const&, T const&);

template <ThreeWayComparable T>
    requires Cpp17LessThanComparable<T>
bool operator<=>(T const&, T const&);
```

For a given type, if `ThreeWayComparable<T>`{:.language-cpp} holds, the expression `p < q`{:.language-cpp} will find both of these operators as candidates (again, despite having different names!). But `operator<=>`{:.language-cpp} is more constrained following the subsumption rules, so it will be preferred.

If `ThreeWayComparable<T>`{:.language-cpp} does not hold, but `Cpp17LessThanComparable<T>`{:.language-cpp} does, then `p < q`{:.language-cpp} only has one viable candidate: `operator<`{:.language-cpp}. Again, as desired. 

That full solution, a `vector<T>`{:.language-cpp} which conditionally provides `<=>`{:.language-cpp} if and only if `T` does - but uses it for all the ordering comparisons, looks like this:

```cpp
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
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

template <ThreeWayComparable T>
    requires Cpp17LessThanComparable<T>
compare_3way_type_t<T> operator<=>(vector<T> const& lhs,
                                   vector<T> const& rhs) {
    return lexicographical_compare_3way(lhs.begin(), lhs.end(),
                                        rhs.begin(), rhs.end());
}
```

I believe this is really the _correct way_ to conditionally provide `operator<=>`{:.language-cpp} for a library type. We still have to write 6 functions (not 10 as I'd previously claimed), we just swapped `operator!=`{:.language-cpp} for `operator<=>`{:.language-cpp}, but we have to be careful about how to properly constrain these operators.

As you can hopefully see by my series of errors in attempting to solve this problem, it's decidedly non-trivial! Unlike my initial attempt in P1186, this solution is optimal. Unlike my second attempt last month, this solution doesn't require gratuitous defaulting of operators.

I had mentioned earlier that `vector<T>`{:.language-cpp} specifically does not currently constrain its comparison operators. Extending `vector` specifically to conditionally adopt `<=>`{:.language-cpp} is even easier, since all you need to do is add a constrained `operator<=>`{:.language-cpp} and you're done; a constrained function is automatically more constrained than an unconstrained one, don't even need any kind of complicated reasoning there.

### Conditionally adopting `operator<=>`{:.language-cpp}, conditional C++20

A slightly more complex topic would be to handle the case where we not only just want Sometimes Spaceship, but we also want a library that can compile in C++17 mode too. For that, we have no choice but to hide the operator behind an `#ifdef`{:.language-cpp}. But what is the right way to do it?

The rule I briefly touched on in the last section - that a constrained function is trivially more constrained than an unconstrained one - turns out to help us mightily. C++17 doesn't have concepts, so no existing operators will use them - they will either be unconstrained or use a mechanism like `std::enable_if`{:.language-cpp} to remove themselves from overload sets as necessary. As a result, all you have to do in this cases is conditionally preprocess our conditional `operator<=>`{:.language-cpp}, as follows:

```cpp
// type traits for == and <, implementation left as an exercise
template <typename T> struct supports_eq;
template <typename T> struct supports_lt;

template <typename T>
enable_if_t<supports_eq<T>::value, bool>
operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

// we need != in C++17, and no point in preprocessing this one out
template <typename T>
enable_if_t<supports_eq<T>::value, bool>
operator!=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs == rhs);
}

template <typename T>
enable_if_t<supports_lt<T>::value, bool>
operator<(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare(lhs.begin(), lhs.end(),
                                   rhs.begin(), rhs.end());
}

template <typename T>
enable_if_t<supports_lt<T>::value, bool>
operator<=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs > rhs);
}

template <typename T>
enable_if_t<supports_lt<T>::value, bool>
operator>(vector<T> const& lhs, vector<T> const& rhs) {
    return rhs < lhs;
}

template <typename T>
enable_if_t<supports_lt<T>::value, bool>
operator>=(vector<T> const& lhs, vector<T> const& rhs) {
    return !(lhs < rhs);
}

// use the feature-test macro to conditionally preprocess
// the spaceship operator (I am not sure at the moment what
// the correct macro is for operator<=>)
#if __cpp_spaceship
template <ThreeWayComparable T>
compare_3way_type_t<T> operator<=>(vector<T> const& lhs,
                                   vector<T> const& rhs) {
    return lexicographical_compare_3way(lhs.begin(), lhs.end(),
                                        rhs.begin(), rhs.end());
}
#endif
```

In C++17, we think of the six two-way comparison functions here as being constrained. In the sense that these functions have static preconditions that, if unmet, lead to these operators being removed from the overload set (i.e. SFINAE).

But with the introduction of Concepts in C++20, the term _constrained_ refers specifically to the use of Concepts (whether named concepts or `requires`{:.language-cpp} clauses). In C++20, those six comparison functions are considered to be _not_ be constrained. The new `operator<=>`{:.language-cpp} on the other hand, is constrained - and hence is more constrained than any of the other binary operators. This ensures that when `operator<=>`{:.language-cpp} is a viable candidate (i.e. when `ThreeWayComparable<T>`{:.language-cpp} holds), that it is the best viable candidate. 

The above implementation does the right thing. In C++17, there will not be an `operator<=>`{:.language-cpp} declared. In C++20, there will be, and it will be used in precisely the cases we want it to be.
