---
layout: post
title: "Unconditionally implementing spaceship"
category: c++
series: operator<=>
tags:
 - c++
 - c++20
 - <=>
--- 

In my [previous post]({% post_url 2018-12-21-spaceship-for-vector %}), I demonstrated how to provide `operator<=>`{:.language-cpp} for a class template conditioned on whether its underlying type provided `operator<=>`{:.language-cpp} (i.e. Sometimes Spaceship). The key insight there was to ensure that `<=>`{:.language-cpp} is _more constrained_ than each of `<`{:.language-cpp}, `>`{:.language-cpp}, `<=`{:.language-cpp}, and `>=`{:.language-cpp}. 

This post will illustrate how to provide `operator<=>`{:.language-cpp} for a class template even if its underlying types do not provide `<=>`{:.language-cpp} (i.e. Always Spaceship). In other words, how to synthesize `<=>`{:.language-cpp} for types you do not even know about. But first, we have to talk about comparison operator equivalence.

There are a lot of equivalences between different comparison expressions that should hold directly based on the definitions of these operators - and we use these equivalences to simplify how we declare the two-way comparison operators today:

- `a == b`{:.language-cpp} is equivalent to `b == a`{:.language-cpp}
- `a != b`{:.language-cpp} is equivalent to `!(a == b)`{:.language-cpp}
- `a < b`{:.language-cpp} is equivalent to `b > a`{:.language-cpp}
- `a <= b`{:.language-cpp} is equivalent to `b >= a`{:.language-cpp}
- `a <= b`{:.language-cpp} is equivalent to `a < b || a == b`{:.language-cpp}

The last one in particular is interesting. The equivalence there follows by definition, indeed "less than or equal to" does, in fact, mean "less than" or "equal to". But that's not typically how we would implement that comparison operator - due to efficiency. It's simply expensive to potentially perform _both_ `<`{:.language-cpp} _and_ `==`{:.language-cpp}. And it's also often simply unnecessary. 

There's a property that some orderings have called _trichotomy_, which means that for two elements `a` and `b`, exactly one of `a < b`{:.language-cpp}, `a == b`{:.language-cpp}, or `a > b`{:.language-cpp} holds. For orderings that have trichotomy, you can define `a <= b`{:.language-cpp} in a more efficient way: saying we're in one of the first two states is exactly equivalent to saying we're _not_ in the third state. In other words:

- `a <= b`{:.language-cpp} is equivalent to `!(b < a)`{:.language-cpp} (when we have trichotomy)

The orders that have trichotomy are called weak orders. Alternatively, orders that don't have trichotomy are partial orders - they're orders for which all of `a < b`{:.language-cpp}, `a == b`{:.language-cpp}, and `a > b`{:.language-cpp} could be `false`{:.language-cpp} (e.g. `float`{:.language-cpp}, where `b` is `NAN`). If you want to learn more than you ever thought there was to know about orders, take some time to read foonathan's series on [mathematics behind comparison](https://foonathan.net/blog/2018/06/20/equivalence-relations.html). There's a lot of good info there. 

The important point here is defining `<=`{:.language-cpp} in terms of negated `<`{:.language-cpp} is only valid for weak orders. But the majority of the standard library does make that assumption. We have blanket wording in [\[operators\]](https://eel.is/c++draft/operators) that says this is how standard library types implement comparisons. `vector<T>`{:.language-cpp} is one such type (the way I showed its implementation in the previous post matches the specification). I just want to make this abundantly clear that today, many standard library types (and algorithms) already assume particular semantics on their types comparisons. `vector<T>`{:.language-cpp}'s comparisons require a weak ordering - they are incorrect for a partial ordering. 

As we attempt to define spaceship for `vector<T>`{:.language-cpp} unconditionally, we will continue to make this assumption. In a way, we are just continuing to make the same assumptions we're already making - just more explicitly. We'll say that for a type that provides `<`{:.language-cpp}, but not `<=>`{:.language-cpp}, we will assume that this is a weak ordering and have `vector<T>::operator<=>`{:.language-cpp} return `std::weak_ordering`.

## Always `operator<=>`{:.language-cpp}, Take 1

The general structure of the solution will follow a fairly simple model: we need `operator==`{:.language-cpp} (the same one we used in the last post), and we need an `operator<=>`{:.language-cpp}. The spaceship operator will be implemented in terms of `std::lexicographical_compare_3way()`{:.language-cpp} - we have this perfectly good algorithm, we should use it. The only thing we really have to figure out is what we actually use for the three-way predicate:

```cpp
// same as we had before
template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

// we now only require <, not full <=>
template <Cpp17LessThanComparable T>
auto operator<=>(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare_3way(
        lhs.begin(), lhs.end(),
        rhs.begin(), rhs.end(),
        /* ???? */
        );
}
```

Now I said at the end of the last section that we will assume that `T` implements a weak ordering, and that that's what we want to synthesize in case `T` doesn't provide `<=>`{:.language-cpp}. How do we do that?

It turns out that one of the other algorithms new to C++20 is one called `std::weak_order(a, b)`{:.language-cpp}. This function always returns `std::weak_ordering`{:.language-cpp} and does:

1. Returns `a <=> b`{:.language-cpp} if that expression is well-formed and convertible to `weak_ordering`.
2. Otherwise, if the expression `a <=> b`{:.language-cpp} is well-formed, then the function is defined as deleted.
3. Otherwise, if the expressions `a == b`{:.language-cpp} and `a < b`{:.language-cpp} are each well-formed and convertible to `bool`{:.language-cpp}, then
    - if `a == b`{:.language-cpp} is `true`{:.language-cpp}, returns `weak_ordering::equivalent`{:.language-cpp};
    - otherwise, if `a < b`{:.language-cpp} is `true`{:.language-cpp}, returns `weak_ordering::less`{:.language-cpp};
    - otherwise, returns `weak_ordering::greater`{:.language-cpp}.
4. Otherwise, the function is defined as deleted.

This seems like what we want right? 

Of course, we can't just pass in `std::weak_order`{:.language-cpp} because C++ doesn't currently just allow you to pass in an overload set... so we have to wrap it in a seemingly redundant lambda: `[](T const& a, T const& b) { return std::weak_order(a, b); }`{:.language-cpp} (typically I'd use `auto`{:.language-cpp}, but in this context we know we have `T`s).

But besides that, how well does this solution do? 

Turns out, not very. 

For one thing, it _always_ returns `std::weak_ordering`{:.language-cpp} (as the name `std::weak_order()`{:.language-cpp} may suggest). We could easily have types (like `int`{:.language-cpp}) that provide a `std::strong_ordering`{:.language-cpp} and it would be a shame to just lose that information.

For another, what do we want to do with those types that provide a `<=>`{:.language-cpp} that returns `std::partial_ordering`{:.language-cpp}? The canonical example is `float`{:.language-cpp}. There are three options for us to consider:

1. We could just reject those entirely. We said we wanted a weak ordering, so we will require a weak ordering. `vector<float>`{:.language-cpp}'s `<=>`{:.language-cpp} should be defined as deleted.
2. We could accept them transparently. We shuold have `vector<float>`{:.language-cpp}'s `<=>`{:.language-cpp} return `std::partial_ordering`{:.language-cpp} by way of using `float`{:.language-cpp}'s built-in directly.
3. We said we wanted a weak ordering, so we should achieve this by lifting the partial ordering into a total ordering. We can do this by saying that any intermediate comparison whose result is `partial_ordering::unordered`{:.language-cpp} is undefined behavior. That is, something like this:

```cpp
std::weak_ordering lift_to_total(float a, float b) {
    // can't use switch here
    // maybe could eventually use Pattern Matching?
    std::partial_ordering cmp = a <=> b;
    if (cmp == std::partial_ordering::greater) {
        return std::weak_ordering::greater;
    } else if (cmp == std::partial_ordering::equivalent) {
        return std::weak_ordering::equivalent;
    } else if (cmp == std::partial_ordering::less) {
        return std::weak_ordering::less;
    } else if (cmp == std::partial_ordering::unordered) {
        [[ assert: false ]];
    }
    __builtin_unreachable();
}
```

Option 1 (the choice we end up making by using `std::weak_order()`{:.language-cpp} in the implementation) seems unnecessarily and pointlessly user-hostile. Options 2 and 3 both seem like strict improvements on the status quo in that both allow us to detect the cases where we'd have a comparison between two elements that are unordered: option 2 allows us to detect this statically (by way of explicitly checking against `std::partial_ordering::unordered`{:.language-cpp}) and option 3 allows us to detect this dynamically (by making this undefined behavior, so at runtime we get an assertion). Today when using `vector<float>`{:.language-cpp}, you'd just get `false`{:.language-cpp} - without a way of knowing whether it was a true `false`{:.language-cpp} or an unorderd `false`{:.language-cpp}.

I have a preference for option 2 here - let's bubble up as much information as possible and let the end-user deal with what to do with the unordered cases. Note that this is the same choice we get when we use Sometimes Spaceship. 

Let's try something else. 

### Always `operator<=>`{:.language-cpp}, Take 2

A different comparison algorithm we have at our disposal is called `std::compare_3way(a, b)`{:.language-cpp}. Instead of always returning `std::weak_ordering`{:.language-cpp}, this one returns the strongest applicable comparison category type:

1. Returns `a <=> b`{:.language-cpp} if that expression is well-formed.
2. Otherwise, if the expressions `a == b`{:.language-cpp} and `a < b`{:.language-cpp} are each well-formed and convertible to `bool`{:.language-cpp}, returns `strong_ordering::equal`{:.language-cpp} when `a == b`{:.language-cpp} is `true`{:.language-cpp}, otherwise returns `strong_ordering::less`{:.language-cpp} when `a < b`{:.language-cpp} is `true`{:.language-cpp}, and otherwise returns `strong_ordering::greater`{:.language-cpp}.
3. Otherwise, if the expression `a == b`{:.language-cpp} is well-formed and convertible to `bool`{:.language-cpp}, returns `strong_equality::equal`{:.language-cpp} when `a == b`{:.language-cpp} is `true`{:.language-cpp}, and otherwise returns `strong_equality::nonequal`{:.language-cpp}.
4. Otherwise, the function is defined as deleted.

As before, we need to use this as the lambda:

```cpp
template <Cpp17LessThanComparable T>
auto operator<=>(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare_3way(
        lhs.begin(), lhs.end(),
        rhs.begin(), rhs.end(),
        [](T const& a, T const& b) {
            return std::compare_3way(a, b);
        });
}
```

This version is quite a bit better. It does the right thing for `int`{:.language-cpp} (the full comparison returns `std::strong_ordering`{:.language-cpp}) and `float`{:.language-cpp} (the full comparison returns `std::partial_ordering`{:.language-cpp}). 

But this still isn't quite right. First, we're synthesizing `std::strong_ordering`{:.language-cpp} for our comparison - when all we said we wanted to assume was a _weak_ ordering. We don't need to assume a _strong_ ordering, and we don't want to convey that kind of assumption downstream of us. 

Second, the way we synthesize that ordering requires both `<`{:.language-cpp} and `==`{:.language-cpp} for `T`. But the comparison functions we're replacing only required `<`{:.language-cpp}. There are many, many types in many, many programs that provide a weak ordering with just `operator<`{:.language-cpp} and it would be a shame if we couldn't use them with our new implementation of `vector<T>`{:.language-cpp}. 

Third, and fairly orthogonal to everything in this post, that 3rd point is somewhat meaningless in a post-[P1185](https://wg21.link/p1185) world where `==`{:.language-cpp} never implicitly calls `<=>`{:.language-cpp} and should probably go. More generally, while [P1186](https://wg21.link/p1186r0) will largely be rewritten for the next mailing, the new revision will still propose replacing `std::compare_3way`{:.language-cpp} the function template with a function object that invokes `<=>`{:.language-cpp} (i.e. the `<=>`{:.language-cpp} equivalent of `std::less<T>`{:.language-cpp}).

### Always `operator<=>`{:.language-cpp}, Take 3

We tried `std::weak_order()`{:.language-cpp} and `std::compare_3way()`{:.language-cpp} and neither is quite adequate. Let's roll our own algorithm and see what we can learn from that.

What I want here is to take the same start that `std::compare_3way()`{:.language-cpp} does: use `<=>`{:.language-cpp} transparently if possible. And then fallback to trying to synthesize a weak ordering one of two ways. Since `==`{:.language-cpp} will typically be faster than `<`{:.language-cpp}, we would like to use if it exists. But if it doesn't exist, we can still just use `<`{:.language-cpp} twice.

With the help of the concepts I introduced in the Sometimes Spaceship post, we can implement this as almost a direct transcription of what I wrote above:

```cpp
struct synthesized_weak_t {
    template <Cpp17LessThanComparable T>
    auto operator()(T const& a, T const& b) const {
        if constexpr (ThreeWayComparable<T>) {
            // if we have <=>, use <=> transparently
            return a <=> b;
        } else if constexpr (Cpp17EqualityComparable<T>) {
            // if we have == (and we already know we have <)
            // synthesize a weak order from those operators
            // this is basically std::weak_order()
            if (a == b) return weak_ordering::equivalent;
            if (a < b)  return weak_ordering::less;
            
            // if we want additional safety, this assertion
            // can ensure that we do in fact have a weak order
            [[ assert: b < a ]];
            return weak_ordering::greater;
        } else {
            // if we don't have ==, we can synthesize a weak
            // order from just calling <. This is basically
            // how vector's operator< works already
            if (a < b) return weak_ordering::less;
            if (b < a) return weak_ordering::greater;
            
            // there isn't anything we can assert in this version
            return weak_ordering::equivalent;
        }
    }
};

inline constexpr synthesized_weak_t synthesized_weak;

template <Cpp17EqualityComparable T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs) {
    return equal(lhs.begin(), lhs.end(),
                 rhs.begin(), rhs.end());
}

template <Cpp17LessThanComparable T>
auto operator<=>(vector<T> const& lhs, vector<T> const& rhs) {
    return lexicographical_compare_3way(
        lhs.begin(), lhs.end(),
        rhs.begin(), rhs.end(),
        // making this a variable is great for usability
        synthesized_weak);
}
```

The above is how I would implement the comparisons for `vector<T>`{:.language-cpp} in a C++20 world. It does the right thing for all types that provide `<=>`{:.language-cpp} directly, and it assumes the bare minimum necessary for types that do not. 

### Always Spaceship for `std::optional<T>`{:.language-cpp}?

I started out by making a big deal about how `vector<T>`{:.language-cpp} already assumes a weak ordering today, so it's more than reasonable to continue to assume a weak ordering in its synthetic implementation of `<=>`{:.language-cpp}. But what about `optional<T>`{:.language-cpp}? It makes no such assumptions. `optional<T>`{:.language-cpp}'s `operator<=`{:.language-cpp} does not forward to its own `operator<`{:.language-cpp}, it instead forwards through to `T`'s `operator<=`{:.language-cpp}. If we want to unconditionally provide `<=>`{:.language-cpp} for `optional<T>`{:.language-cpp}, how would we do that?

Great question.

If we assume a weak ordering with the above implementation and `T` actually only has a partial order, we would get wrong answers and the occasional assertion. If we assume a partial ordering and `T` actually has a total order, we'd always provide correct answers but likely perform many completely unnecessary comparisons.

The safest bet is, without question, to only do Sometimes Spaceship for `std::optional<T>`{:.language-cpp}. It is arguably important to not introduce new assumptions. For `std::vector<T>`{:.language-cpp}, the Always Spaceship path is on firmer ground.

At least, we can make one improvement without risk: we can use `<=>`{:.language-cpp} unconditionally to compare `optional<T>`{:.language-cpp} to `std::nullopt_t`{:.language-cpp}:

```cpp
// note that this is unconstrained
template <typename T>
bool operator==(optional<T> const& lhs, nullopt_t) {
    return !lhs.has_value();
}

// note that this is also unconstrained
template <typename T>
strong_ordering operator<=>(optional<T> const& lhs, nullopt_t) {
    return lhs.has_value() <=> false;
}
```

The only other types in the standard library that do not assume a weak ordering are `variant<Ts...>`{:.language-cpp} and, surprisingly, `stack<T, Container>`{:.language-cpp} and `queue<T, Container>`{:.language-cpp}. I didn't even realize `stack` and `queue` _had_ comparisons defined!

### Always Spaceship for `std::tuple<Ts...>`{:.language-cpp}?

Unlike `optional<T>`{:.language-cpp}, and like `vector<T>`, `tuple<Ts...>`{:.language-cpp} assumes a total ordering. And so `tuple<Ts...>`{:.language-cpp} would be a safe candidate for Always Spaceship.

This has the interesting consequence that if make this choice, it makes it easier to adopt weak orderings for those cases where we just want the default, memberwise, lexicographical comparison. One of the examples I used in [P1186R0](https://wg21.link/p1186r0) and in [Improvements to `<=>`{:.language-cpp}]({% post_url 2018-11-12-improve-spaceship %}) was a simple aggregate:

```cpp
// some perfectly functional C++17 type that implements
//  a total order
struct Ordered {
    bool operator==(Ordered const&) const { ... }
    bool operator<(Ordered const&) const { ... }
};

struct Aggr {
    int i;
    char c;
    Ordered o;

    auto operator<=>(Aggr const&) const = default;
};
```

As-is, `<=>`{:.language-cpp} for `Aggr` is defined as deleted because `Ordered` has no `<=>`{:.language-cpp}. But if we're happy with just assuming that `Ordered` provides a weak total order, instead of a strict total order, then we can just take advantage of `tuple`'s new-found Always Spaceship:

```cpp
auto Aggr::operator<=>(Aggr const& rhs) const {
    auto tied = [](Aggr const& e){
        return std::tie(e.i, e.c, e.o);
    };
    return tied(*this) <=> tied(rhs);
}
```

If and when `Ordered` ever adopts an `operator<=>`{:.language-cpp} of its own, the implementation above will silently and transparently switch to using it. This may be annoying boilerplate, but it just does the right thing.

However, if we know that `Ordered` provides a strong order and want to forward that information through `Aggr` - or if we know that it provides a partial order and want to ensure that we are providing the correct answers - this implementation would be wrong. We would have to do something more involved to do the right thing, something that I'll save for a future post.

### Conclusion

Many class templates will implement `p <= q`{:.language-cpp} in terms of `!(q < p)`{:.language-cpp}. This transformation is only valid for total orders (i.e. weak or strong, not partial). Those types can safely take the Always Spaceship route - replacing the implementations of `<`{:.language-cpp}, `>`{:.language-cpp}, `<=`{:.language-cpp}, and `>=`{:.language-cpp} with one `operator<=>`{:.language-cpp}, constrained on `Cpp17LessThanComparable`, that is implemented in terms of either `synthesized_weak()`{:.language-cpp} or `synthesized_strong()`{:.language-cpp}. This design reduces the amount of code we have to write, and provides an easy adoption path for types that will eventually provide `<=>`{:.language-cpp}. 

For those types that transparently forward `<=`{:.language-cpp}, going the Always Spaceship route is not as safe, since no assumptions are being made that you can take advantage of. It's of course _doable_. You just have to be cognisant that either you're making new assumptions (i.e. assuming a weak or even a strong order) or potentially invoking more comparisons (i.e. if you want to take the safe route and merely assume a weak order). If neither of these choices is palatable, going the Sometimes Spaceship route is always safe - it just always involves more code.