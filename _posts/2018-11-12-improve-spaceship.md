---
layout: post
title: "Improvements to <=>"
category: c++
tags:
 - c++
 - c++20
 - <=>
--- 

Last week, the C++ Standards Committee met in San Diego to work on C++20. One of my own main goals was to discuss two papers I wrote making improvements to a new language feature for C++20: `operator <=>`{:.language-cpp}, also known as the three-way comparison operator but better known as the spaceship operator. There were two serious problems with spaceship that I set out to address: [performance](#p1185) and [usability](#p1186). I wanted to take the time to describe the problems I'm trying to solve, my solutions to them, what the committee thought about both, and what could happen in the future. 

### <a name="p1185"/>[P1185: `<=> != ==`{:.language-cpp}](https://wg21.link/p1185r0)

David Stone was the first person that pointed out that there are some performance issues with the spaceship operator, in what would eventually become [P1190: I did not order this! Why is it on my bill?](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1190r0.html). Here is a short description of the problem. 

Consider a type like `std::vector<T>`{:.language-cpp}. Since the promise of `<=>`{:.language-cpp} is that we only have to write _one_ operator function instead of _six_ operator functions, it is quite tempting to just scrap the ones we have and write this (simplified to just assume `strong_ordering` for the purposes of this example):

```cpp
template<typename T>
strong_ordering operator<=>(vector<T> const& lhs, vector<T> const& rhs) {
    size_t min_size = min(lhs.size(), rhs.size());
    for (size_t i = 0; i != min_size; ++i) {
        if (auto const cmp = lhs[i] <=> rhs[i]; cmp != 0) {
            return cmp;
        }
    }
    return lhs.size() <=> rhs.size();
}
```

In many ways, this is really nice. It's pretty short, easy to follow, gives us the correct answer for every test. And for ordering, it's as good as you can get. But it turns out it's pretty bad for equality. Because for types like `vector`, you can short-circuit: two `vector`s that have different sizes are clearly unequal, you don't have to even look at any of the elements. We definitely want to provide an `==`{:.language-cpp}, but this is just something we have to know and be very vigilant about doing - because `==`{:.language-cpp} with just spaceship (a) compiles and (b) gives the correct answer. But okay, we're C++ programmers, we can be vigilant, so let's write that:

```cpp
template<typename T>
bool operator==(vector<T> const& lhs, vector<T> const& rhs)
{
    // short-circuit on size early
    const size_t size = lhs.size();
    if (size != rhs.size()) {
        return false;
    }

    for (size_t i = 0; i != size; ++i) {
        // use ==, not <=>, in all nested comparisons
        if (!(lhs[i] == rhs[i])) {
            return false;
        }
    }

    return true;
}
```

Actually, this _still_ isn't enough, because while we get fast `==`{:.language-cpp}, we will end up with slow `!=`{:.language-cpp}... because `v1 != v2`{:.language-cpp} will end up doing `(v1 <=> v2) != 0`{:.language-cpp} per the rules in the working draft, so we _also_ have to provide an `operator!=()`{:.language-cpp} that just calls `==`{:.language-cpp}.

The above is all compellingly bad, but you can figure that only experts write containers, so only experts have to worry about ensuring that we remember to implement all the operators. Until we start thinking about other types:

```cpp
struct S {
    vector<string> names;
    auto operator<=>(S const&) const = default;
};
```

What happens when I do `s1 == s2`{:.language-cpp}? We spent the time to ensure that `vector` equality comparisons are fast... but that's not what happens here. We only provided a defaulted `<=>`{:.language-cpp}, so what happens is we end up doing `(s1.names <=> s2.names) == 0`. We call slow `vector` spaceship, which calls slow `string` spaceship. The only way to get the performance we want is to ensure that we also write equality for `S`.

Like this?

```cpp
struct S {
    vector<string> names;
    auto operator<=>(S const&) const = default;
    bool operator==(S const&) const = default;
};
```

This is the biggest illusion of success, since it turns out that defaulted `==`{:.language-cpp} just calls `<=>`{:.language-cpp} anyway. The only way to get this to work is to hand-write both `==`{:.language-cpp} (to do memberwise equality) and `!=`{:.language-cpp} (to invoke `==`{:.language-cpp}). And you have to write this for every compound type that could have any subobject, that itself could have any subobject recursively all the way down, which can implement `==`{:.language-cpp} more efficiently than `<=>`{:.language-cpp}. That is an enormous burden that nobody could even meet. And if anyone, anywhere in your subobject hierarchy forgets to do this, you transition from `==`{:.language-cpp} to `<=>`{:.language-cpp} and it's all over. 

My solution to this was [P1185](https://wg21.link/p1185r0), which has four parts:

1. Never synthesize a call to `<=>`{:.language-cpp} from either `a == b`{:.language-cpp} or `a != b`{:.language-cpp}. These can only rewrite to other `==`{:.language-cpp} candidates (e.g. `a != b`{:.language-cpp} could end up calling `!(b == a)`{:.language-cpp}, but never any kind of `<=>`{:.language-cpp}).
2. A defaulted `==`{:.language-cpp} operator function should do memberwise equality. A defaulted `!=`{:.language-cpp} operator function shuld invoke `==`{:.language-cpp}, negated.
3. Change the definition of _strong structural equality_ to be based on defaulted `==`{:.language-cpp} instead of defaulted `<=>`{:.language-cpp}. I mean, it's called strong structural _equality_ right?
4. Allow defaulted `<=>`{:.language-cpp} to implicitly generate defaulted `==`{:.language-cpp}, so that at least in the easy case you only have to write one function.

Evolution was strongly in favor of this change. We polled parts 1-3 separately from part 4, with the first three parts accepted 24-0 and the latter 16-4 (the argument against is that we now have one declaration that actually declares two things).

Jens "Master Wordsmith" Maurer helped me formulate the wording, and Core reviewed it. There is still one open design question, regarding part 4: if the defaulted `<=>`{:.language-cpp} is defined as deleted, what do you do? Do you still implicitly generate a defaulted `==`{:.language-cpp} or not? Once this question is resolved, and worded properly in whichever direction we go, it is pretty likely that this paper will be adopted to the working draft in Kona. 

I think this is a large, unambiguous improvement to `operator<=>()`{:.language-cpp}, avoiding the pessimization trap entirely.

### <a name="p1186"/>[P1186: When do you actually use `<=>`{:.language-cpp}?](https://wg21.link/p1186r0)

The previous paper was approved unanimously (at least the important parts), with no objection to the direction from Core, or really from anyone else. This one had a very, very different fate.

`<=>`{:.language-cpp} as an operator is somewhat viral. In order to implement `<=>`{:.language-cpp} for a compound type, all of its constituents need to have their own `<=>`{:.language-cpp} implemented. Many years from now, when everyone's ordered types will have transitioned to C++20, this won't be a problem at all, and everything will work seamlessly. Until then, no types actually provide `<=>`{:.language-cpp} (except the core language types), so we're a little stuck. 

Let's say I have a type `Ordered`, which defines all six comparison operators. And I want to stick it into an aggregate, and just give it a default, lexicographic, member-wise ordering. I want to write:

```cpp
struct Aggr {
    int i;
    char c;
    Ordered o;
    
    auto operator<=>(Aggr const&) const = default;
};
```

The problem is, that `<=>`{:.language-cpp} is defined as deleted, because `Ordered` isn't spaceshipable. I can't just default spaceship - I have to completely handwrite it, even though I only want "the obvious thing":

```cpp
???? operator<=>(Aggr const& rhs) const {
    if (auto cmp = i <=> rhs.i; cmp != 0) return cmp;
    if (auto cmp = c <=> rhs.c; cmp != 0) return cmp;
    return std::compare_3way(o, rhs.o);
}
```

This is pretty verbose (though generally better than we could write in C++17). You have to keep track of which types _are_ spaceship-able (`int`{:.language-cpp} and `char`{:.language-cpp}) and which aren't, and you have to know the right magic library fallback (`std::compare_3way`{:.language-cpp}). And what do you put in the return type there? I just left it at `????` because that's a pain too. 

It's no better for generic library either. Take something like `std::pair<T,U>`{:.language-cpp}, it's very tempting to write:

```cpp
template <typename T, typename U>
struct pair {
    T first;
    U second;
    
    bool operator==(pair const&) const = default; // thanks to P1185
    auto operator<=>(pair const&) const = default;
};
```

And this works... if `T` and `U` are both spaceship-able. My `pair<int, int>`{:.language-cpp}s are orderable, but not my `pair<int, Ordered>`{:.language-cpp}s. 

The argument I made in [P1186](https://wg21.link/p1186r0) was as follows: in order to implement `<=>`{:.language-cpp} for any of these types, you'd have to fallback to `std::compare_3way()`{:.language-cpp} sufficiently often that you'd basically use it unconditionally to minimize cognitive overhead. And there isn't much of another choice - if you conditionally provide `<=>`{:.language-cpp}, you'd have to also conditionally provide `<`{:.language-cpp} (so that pre-`<=>`{:.language-cpp} types still work), which would in turn end up pessimizing `<`{:.language-cpp} because that implementation wouldn't use `<=>`{:.language-cpp}. 

To see why this is a pessimization, consider a type like `string`{:.language-cpp} that would have an efficient `<=>`{:.language-cpp}. Invoking `s1 <=> s2`{:.language-cpp} would have to walk the `string` (at most) one time. But if we're doing `operator<`{:.language-cpp} in the context of, for instance, comparing the first element of a `pair`, we'd have to try potentially both `s1 < s2`{:.language-cpp} and `s2 < s1`{:.language-cpp}. In the worst case (when `s1 == s2`{:.language-cpp}), this ends up walking both `string`s twice. That's a lot more work. 

The end result of that is: the only place you could use `<=>`{:.language-cpp} would be to implement `std::compare_3way()`{:.language-cpp}. In order to make `<=>`{:.language-cpp} actually useful, we need to lift that library magic into the language. 

The proposal in P1186 was to redefine `a <=> b`{:.language-cpp} to fall-back to trying `<`{:.language-cpp} and `==`{:.language-cpp} if those are both valid (and assume `strong_ordering`) or fall-back further to trying just `==`{:.language-cpp} if that's valid (and assume `strong_equality`). This allows just defaulting `<=>`{:.language-cpp} for both `pair` and `Aggr` to do the right thing. 

The downside is that we're assuming semantics based on syntax. Just because you write `<`{:.language-cpp} and `==`{:.language-cpp} for your type does not mean you have a strong ordering. You might just have a partial ordering. Just because you write `==`{:.language-cpp} does not mean you have strong equality (despite Tony's protestations that [`weak_equality` is harmful](http://open-std.org/JTC1/SC22/WG21/docs/papers/2018/p1307r0.pdf)). 

After a long discussion in Evolution, the room decided that the benefits (usability of `<=>`{:.language-cpp}) sufficiently outweighed the harm (the core language guessing at your types' semantics, and likely getting it wrong a lot, leading to unexpected comparison category strengthening) and approve the proposal, by a vote of 18-1.

The wording for this paper, unlike P1185, was pretty easy: just one paragraph to add to [over.match.oper]. I could word that one just fine on my own. 

And then I brought it to Core.

And everyone in Core thought that this was a terrible idea. **Everyone**. They really, strongly disliked the comparison category strengthening.

And, in general, really strongly disliked having the core language guess at user type semantics. And if we were going to start guessing about user semantics, we should at least make the weakest possible guess - not the strongest possible guess. That is, instead of guessing `strong_ordering` and `strong_equality`, we could at least guess `partial_ordering` and `weak_equality`. That could be a design that they could live with - they wouldn't necessarily love it, but they could live with it.

This was something I had not considered at all. I would have been quite happy to accept that direction (after all, it still allows both defaulting `<=>`{:.language-cpp} and using it in generic code, which was the problem I was trying to solve)... but after talking to more and more people about it after the fact, I started realizing how much of the design space I had not considered... or worse, had mis-considered. And I'm not sure even the `partial_ordering`/`weak_equality` direction is a good way to go.

### Starting over

I wanted to go back to the drawing board. One of the things I had mis-considered was the conditional provision of operators. I had convinced myself that conditionally providing `<=>`{:.language-cpp} for a class template while also conditionally providing `<`{:.language-cpp} would mean writing something like this:

```cpp
template <typename T, typename U>
struct pair {
    T first;
    U second;
    
    // provide <=> if T and U have <=>
    common_comparison_category_t<
        compare_3way_type_t<T>, // see P1187
        compare_3way_type_t<U>
    > operator<=>(pair const& rhs) const {
        if (auto cmp = first <=> rhs.first; cmp != 0) return cmp;
        return second <=> rhs.second;
    }
    
    // provide < if T and U have <
    auto operator<(pair const& rhs) const
        -> decltype(first < rhs.first && second < rhs.second)
    {
        if (first < rhs.first) return true;
        if (rhs.first < first) return false;
        return second < rhs.second;
    }
};
```

That is, `pair` conditionally provides `<=>`{:.language-cpp} and also conditionally provides `<`{:.language-cpp}. This means that an expression like `p1 < p2`{:.language-cpp} would invoke `operator<`{:.language-cpp} (since if `<=>`{:.language-cpp} exists, `<`{:.language-cpp} does too). But we want to avoid that happening because it's a pessimization (as described earlier).

But that's not really the right choice. We do want to conditionally provide `<`{:.language-cpp} and `<=>`{:.language-cpp}, but it is possible to avoid the potential pitfall with `<`{:.language-cpp} by writing something like the following (which is, admittedly, quite verbose, but better to start correct):

```cpp
template <typename T>
concept ThreeWayComparable = requires (T const t) {
    { t <=> t };
};

template <typename T, typename Cat>
concept ThreeWayComparableAs = ThreeWayComparable<T> && requires(T const t) {
    { t <=> t } -> Cat;
};

// We need a partial_ordering - which can either come from <=> or 
// can be synthesized from two calls to <. That is enough for pair
template <ThreeWayComparableAs<partial_ordering> T>
auto partial_from_less(T const& lhs, T const& rhs) {
    return lhs <=> rhs;
}

template <ThreeWayComparable T>
auto partial_from_less(T const&, T const&) = delete;

template <typename T>
partial_ordering partial_from_less(T const& lhs, T const& rhs)
{
    if (lhs < rhs) return partial_ordering::less;
    if (rhs < lhs) return partial_ordering::greater;
    return partial_ordering::equivalent;
}

template <typename T, typename U>
struct pair {
    T first;
    U second;

    // == and != by default is fine, courtesy of P1185
    bool operator==(pair const&) const = default;
    
    // legacy version
    bool operator<(pair const& rhs) const {
        if (auto cmp = partial_from_less(first, rhs.first); cmp != 0) {
            return cmp < 0;
        }
        return second < rhs.second;
    }
    bool operator>(pair const& rhs) const { return rhs < lhs; }
    bool operator<=(pair const& rhs) const { return !(rhs < lhs); }
    bool operator>=(pair const& rhs) const { return !(lhs < rhs); }
    
    // <=> version, all defaulted
    auto operator<=>(pair const&) const = default;
    bool operator<(pair const&) const requires ThreeWayComparable<T> && ThreeWayComparable<U> = default;
    bool operator>(pair const&) const requires ThreeWayComparable<T> && ThreeWayComparable<U> = default;
    bool operator<=(pair const&) const requires ThreeWayComparable<T> && ThreeWayComparable<U> = default;
    bool operator>=(pair const&) const requires ThreeWayComparable<T> && ThreeWayComparable<U> = default;
};
```

Alright, what's going on here. The promise of `<=>`{:.language-cpp} was that instead of writing 6 comparison operators, we only have to write 1. But up here, I'm writing 10. If our types _both_ provide `<=>`{:.language-cpp}, all the defaults are fine. But if they don't, we need to fall-back to unconstrained versions (the constrained ones are to ensure that `<`{:.language-cpp} forwards to `<=>`{:.language-cpp} to avoid the pessimization I mentioned earlier). 

The unconstrained `<`{:.language-cpp} could have simply invoked `<`{:.language-cpp} in both directions, like it does for `pair`{:.language-cpp} today. However, it's possible that we have a `T`{:.language-cpp} that provides `<=>`{:.language-cpp}, even if `U`{:.language-cpp} does not, in which case we want to take advantage of the potential optimization by using `T`{:.language-cpp}'s `<=>`{:.language-cpp}. That's what `partial_from_less()`{:.language-cpp} is doing here - it's a... partial.... opt-in to `<=>`{:.language-cpp} (the choice of requiring a `partial_ordering` instead of a `weak_ordering` doesn't matter too much in this context).

As far as I'm aware, this implementation maintains the current behavior for all types, does not lie about its comparison category (it only provides `<=>`{:.language-cpp} if both `T` and `U` do), and is as efficient as possible.

But it's so verbose.

And the best you can do for `Aggr` would probably be something like:

```cpp
template <typename T>
struct assume_strong {
    T const& val;
    
    strong_ordering operator<=>(assume_strong const& rhs)
        requires ThreeWayComparableAs<T, strong_ordering>
        = default;
        
    auto operator<=>(assume_strong const&)
        requires ThreeWayComparable<T>
        = delete;
    
    strong_ordering operator<=>(assume_strong const& rhs) const {
        if (val == rhs.val) return strong_ordering::equal;
        if (val < rhs.val) return strong_ordering::less;
        return strong_ordering::greater;
    }
};

struct Aggr {
    int i;
    char c;
    Ordered o;
    
    bool operator==(Aggr const&) const = default;
    
    auto operator<=>(Aggr const& rhs) const {
        auto tied = [](Aggr const& a) {
            return make_tuple(ref(a.i), ref(a.c), assume_strong{a.o});
        };
        return tied(*this) <=> tied(rhs);
    }
};
```

I have to list all my members, but with this fairly light-weight library helper (and CTAD extension by way of either the [P0960](https://wg21.link/p0960) or [P1021](https://wg21.link/p1021)), but at least I only have to list them once and this does the right thing without me having to manually compute the comparison category. With the above implementation of `assume_strong`, I even get some nice forward compatibility:
- when `Ordered` adds `<=>`{:.language-cpp}, I pick it up for free - `Aggr` will be optimal
- if `Ordered` adds `<=>`{:.language-cpp} in a way that ends up _not_ being `strong_ordering`, I get a compile error. Also great!

But while they work, these implementations of `pair` and `Aggr` are the furthest thing from easy to use. That's a lot of code. It's quite complex, and I don't think it even remotely approaches the bar that I set out to clear as far as usability goes. I would like to be able to write much, much less code than this. I would like people new to C++ to be able to easily add comparisons to their types without having to resort to... that.

So what can we do?

The first thing that jumped into mind for me was attempting to reduce the number of operators we have to write. For `pair`, there's really only 4 interesting ones:

- `==`{:.language-cpp}, defaulted
- `<=>`{:.language-cpp}, defaulted
- `<`{:.language-cpp}, manual
- `<`{:.language-cpp}, constrained and defaulted

The other 6 operators are either constrained and defaulted, or redirect to `<`{:.language-cpp}. Maybe we could add fall-backs there? That is, have `p > q`{:.language-cpp} fall-back to `q < p`{:.language-cpp}. That is easy to do, since those two are surely equivalent.

But we run into problems with `p <= q`{:.language-cpp}. For a weak order, that is equivalent to `!(q < p)`{:.language-cpp}. But for a partial order, you'd need `p == q || p < q`{:.language-cpp}. How do you know which to choose? The former is obviously more performant, the latter is more correct - but picking the former is assuming semantics on a type. Exactly the problem I ran into initially with P1186.

### A different kind of default

Let's look at `Aggr` instead. P1186 wanted to support just writing:

```cpp
stuct Aggr {
    int i;
    char c;
    Ordered o;
    
    auto operator<=>(Aggr const&) = default;
};
```

But what if instead of having the language make assumptions, you force the user to state their intent. This idea was something Tony suggested while we were getting on the plane late Saturday night in San Diego:

```cpp
stuct Aggr {
    int i;
    char c;
    Ordered o;
    
    strong_ordering // I do solemnly swear that Ordered
                    // implements a strong_ordering
    operator<=>(Aggr const&) = default;
};
```

When specifying a type for defaulted `<=>`{:.language-cpp}, the language could check that each member is spaceship-able. If it is, then use that `<=>`{:.language-cpp} and ensure that it fits the category. Otherwise, synthesize what the user asked for from the operators provided. If `Ordered` did not have a `<`{:.language-cpp} or `==`{:.language-cpp}, this would be ill-formed. In this way, the core language isn't guessing - it's doing what it's told. And when `Ordered` does provide its own `<=>`{:.language-cpp} and it ends up being `partial_ordering` instead, this becomes a compile error. Great! For this situation, the user is stating their own semantics - neither the language nor the library has to guess at anything. 

Can we use something like this to help define `pair`? Turns out, yeah. Richard Smith suggests that we can make a type trait like `cat_with_fallback<T>`{:.language-cpp}, whose type is:
- `decltype(t <=> t)`{:.language-cpp} if that exists
- `partial_ordering`{:.language-cpp} if `decltype(t < t)`{:.language-cpp} is `bool`{:.language-cpp}
- `void`{:.language-cpp} otherwise

And then all we need is:

```cpp
template <typename T, typename U>
struct pair {
    T first;
    U second;
    
    bool operator==(pair const&) const = default;
    
    common_comparison_category_t<
        cat_with_fallback<T>,
        cat_with_fallback<U>
    > operator<=>(pair const&) const = default;
};
```

Here, the library (rather than the core language) is guessing at type semantics, and it's doing so pessimistically. However, `partial_ordering` probably isn't the right assumption for the library types. For a `pair`, `p1 <= p2`{:.language-cpp} invokes `!(p2 < p1)`{:.language-cpp}. That is, it requires a total order, even if it's not specified as such. For all the containers, `<`{:.language-cpp} is [required](http://eel.is/c++draft/containers#tab:containers.optional.operations) to be a total order. So a better choice for `cat_with_fallback` for the library could be:
- `decltype(t <=> t)`{:.language-cpp} if that exists
- `weak_ordering`{:.language-cpp} if `decltype(t < t)`{:.language-cpp} is `bool`{:.language-cpp}
- `void`{:.language-cpp} otherwise


Ok, well, that's a simple example. What about something more complex like `std::vector<T>`{:.language-cpp}? We can do that too:

```cpp
template <typename T>
struct with_fallback {
    T const& t;
    
    cat_with_fallback<T> operator<=>(with_fallback const&) const = default;
};

template <typename T>
cat_with_fallback<T> operator<=>(vector<T> const& lhs, vector<T> const& rhs)
{
    size_t min_size = min(lhs.size(), rhs.size());
    for (size_t i = 0; i != min_size; ++i) {
        if (auto cmp = with_fallback{lhs[i]} <=> with_fallback{rhs[i]};
                cmp != 0)
        {
            return cmp;
        }
    }
    return lhs.size() <=> rhs.size();
}
```

Note that this is _almost_ as short as the initial example. Just instead of directly `<=>`{:.language-cpp}-ing the elements of the two `vector`s, I'm doing it on `with_fallback`s. This is again a pessimistic fall-back to assuming just a partial or weak ordering, but that's sufficient to implement this optimally for both cases.

So here we are, actually using `<=>`{:.language-cpp} to implement `pair` and `vector` (mostly), and actually being able to default `<=>`{:.language-cpp} in the cases that should be defaulted. It's not as nice as P1186 simply being able to use `lhs[i] <=> rhs[i]`{:.language-cpp}, but we avoid having to resort to the core language guessing at semantics. 

There are obviously many details left to consider (like what _exactly_ this synthetic `<=>`{:.language-cpp} should do and how, which comparison category should the library "guess" - `partial` vs `weak` vs `strong`), but this is the direction I'm currently leaning towards pursuing in Kona. I consider this to be a much better direction than the one I came to San Diego with in P1186, and I am grateful to Core for having rejected that paper.

Good idea? Bad idea? Intriguing? Would love to hear thoughts.
