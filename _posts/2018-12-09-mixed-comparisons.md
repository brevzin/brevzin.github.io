---
layout: post
title: "Getting in trouble with mixed comparisons"
category: c++
tags:
 - c++
 - c++17
 - optional
--- 

Andrzej has a great [new post](https://akrzemi1.wordpress.com/2018/12/09/deducing-your-intentions/) about the difficulty that arises when the language or the library tries to make assumptions about programmer intent. He brings up two examples of this difficulty:
- should CTAD wrap or copy?
- how should `optional`{:.language-cpp}'s mixed comparison behave?

I've touched on the first topic in an earlier post on [CTAD quirks]({% post_url 2018-09-01-quirks-ctad %}), and I wanted to write some words about the latter topic here - since I think it's really interesting.

Mixed comparisons are very closely related to implicit conversions, which themselves are always going to be a difficult topic. Let's just start on the low end and work our way up, with just the `int`{:.language-cpp}s:

```cpp
bool f1(int a, long b) {
  return a == b;
}
```

Unless you take the view that implicit conversions are _always_ wrong, and thus that mixed conversions should _never_ happen (which is an extreme view in terms of the range of possible opinions to have, but isn't totally outrageous), this is a perfectly reasonable function. `a` and `b` have different types, but represent the Same Platonic Thing. We can convert from `int`{:.language-cpp} to `long`{:.language-cpp} both cheaply and without any information loss. There aren't any weird caveats with comparing an `int`{:.language-cpp} to a `long`{:.language-cpp}. It just works and does the sensible thing. 

Let's go one step outwards:

```cpp
bool f2(optional<int> a, optional<int> b) {
    return a == b;
}
```

The only reason to reject this example would be if you think that `optional<T>`{:.language-cpp} shouldn't have any comparisons at all under any circumstances. I don't know of anybody who has expressed that view. This function also has a clear and sensible meaning, `a == b`{:.language-cpp} if either `a` and `b` are both disengaged or both are engaged with the same underlying `int`{:.language-cpp} value.

Let's go one step further:

```cpp
bool f3(optional<int> a, optional<long> b) {
    return a == b;
}
```

This one is more interesting. The underlying comparison here is equivalent to `f1()`{:.language-cpp}: either both `optional`s are disengaged or both are engaged and we do the mixed-integer comparison. If we think that comparison is sensible, surely this one should be as well? We've added a wrapping layer here, but we haven't actually added any kind of additional semantics that would break our notion of Same Platonic Thing.

Now what about this one:

```cpp
bool f4(optional<int> a, int b) {
    return a == b;
}
```

This is a different kind of mixed comparison than the ones in `f1()`{:.language-cpp} and `f3()`{:.language-cpp}. But I think you can still make the argument that this comparison has an obvious meaning: `a` is engaged and its underlying value is the same as `b`. This is a perfectly reasonable semantic, and there really is no other meaning this comparison could take on. Outside of being ill-formed, that is. Since `optional<int>`{:.language-cpp} is implicitly constructible from `int`{:.language-cpp}, if `optional<T>`{:.language-cpp}'s comparison operators as declared as non-member friends, then you get this comparison even without asking for it. 

And what about this one:

```cpp
bool f5(optional<int> a, long b) {
    return a == b;
}
```

If you allow `f3()`{:.language-cpp} (a mixed-optional comparison) and `f4()`{:.language-cpp} (an optional-value comparison), then you _must_ allow this one right? Arguably, we're still making perfectly sensible decisions with each step here. Every comparison presented thus far does have one, clear semantic meaning - with no weird quirks, caveats, or edge cases.

So far, so good right?

<hr />

But what happens when we do this:

```cpp
bool f6(optional<optional<int>> a, optional<int> b) {
    return a == b;
}
```

Think about this for a minute. In particular, what should the value of `f6(nullopt, nullopt)`{:.language-cpp} actually be? This is basically the case that Andrzej brought up at the end of his post. It's tempting to say the answer is obvious, but it's surprisingly not. There are two different ways of thinking about this:

1. This is a special case of `f3()`{:.language-cpp}: comparing `optional<T>`{:.language-cpp} to `optional<U>`{:.language-cpp} for types `T` and `U` that are comparable (in this case `T=optional<int>`{:.language-cpp} and `U=int`{:.language-cpp}, which is the `f4()`{:.language-cpp} comparison). If we think about it in these terms, then the result of `f6(nullopt, nullopt)`{:.language-cpp} should be `true`{:.language-cpp} because we have two disengaged `optional`s, so they are equal.
2. This is a special case of `f4()`{:.language-cpp}: comparing `optional<T>`{:.language-cpp} to `T` for type `T` that is comparable (in his case `T=optional<int>`{:.language-cpp}). If we think about it in these terms, then the result of `f6(nullopt, nullopt)`{:.language-cpp} is `false`{:.language-cpp} because the `a` is disengaged - so it cannot compare equal to a value. 

Which is the correct answer?

The Standard Library picks option 1 by way of allowing mixed-optional comparisons. Boost does not support mixed-optional comparisons (`f3()`{:.language-cpp} does not compile using `boost::optional`{:.language-cpp}), so it picks option 2. I'm not sure either of these options is more defensible than the other.

A third different, arguably defensible implementation strategy would be to allow mixed-optional comparisons (like `f3()`{:.language-cpp}) but disallow mixed-category comparisons (like `f4()`{:.language-cpp}), in which case `f6()`{:.language-cpp} wouldn't compile. There is an open source implementation that makes this choice (Basit Ayantunde's [SKX](https://github.com/lamarrr/STX)) and it has its own inconsistency: `f4()`{:.language-cpp} does not compile, but if the body of `f4()`{:.language-cpp} used `f2(a,b)`{:.language-cpp} instead of `a == b`{:.language-cpp}, it would have? But if you disallowed implicit conversions (that is, `optional<int>`{:.language-cpp}'s value constructor is `explicit`{:.language-cpp}), then allowing `f3()`{:.language-cpp} but disallowing both `f4()`{:.language-cpp} and `f6()`{:.language-cpp} would be both reasonable and consistent.

What's the moral of this post? I am not sure. Even making a couple of really sensibly and easily defensible decisions (allowing comparing `optional<int>`{:.language-cpp} to both `long`{:.language-cpp} and `optional<long>`{:.language-cpp}) still leads us to a situation where there just is no right answer. What did the programmer actually want `f6()`{:.language-cpp} to mean? In this case, the programmer may not even know what they wanted! Is that a reason in of itself to view this as a library defect and try to prevent this particular kind of comparisons? I do not know. Ultimately, I just thought this was an interesting dilemma and wanted to share.
 
