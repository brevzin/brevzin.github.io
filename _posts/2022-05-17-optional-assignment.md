---
layout: post
title: "Assignment for <code class=\"language-cpp\">optional&lt;T></code>"
html_title: Assignment for optional<T>
category: c++
tags:
 - c++
 - c++20
 - optional
pubdraft: yes
permalink: opt-assign
---

Let's talk about assignment for `optional<T>`. I realize this is a fraught topic, but I want to try to build up proper intuition about how assignment has to work, especially since the debate around this topic has been fairly underwhelming. This post will almost exclusively discuss copy assignment (i.e. the one that takes an `optional<T> const&`), since everything just follows from that.

As a quick intro, I am going to use the following layout:

```cpp
template <typename T>
class Optional {
    union {
        T value_;
    };
    bool has_value_;
};
```

In C++17, you'd see an additional empty object in the `union` to satisfy `constexpr` initialization requirements, but that's no longer the case in C++20 after [P1331](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2019/p1331r2.pdf) ([demo](https://godbolt.org/z/Mo5aPznYd)). This is sufficient. There are many different possible terms to refer to the states that an `Optional` can take (some from languages, like `Just`/`Nothing` in Haskell or `Some`/`None` in Rust); the ones that I am going to use here are _engaged_ and _disengaged_.

### Copy Assignment for `Optional<T>`

The goal of copy assignment is that after `lhs = rhs;`, `rhs` is not modified and `lhs` has the same value as `rhs`. What it means to "have the same value as" another object is kind of handwavy though, and most attempts to define it end up being circular. You know it when you see it, I guess. But we can at least say something definitely here: the end result is that the left-hand `Optional` is in the same state as the right-hand `Optional` and, if both are engaged, that their underyling values are the same.

In order to implement this, we have to consider the cartesian product of all the states and consider them separately. Thankfully, three of these four possibilities (those with at least one of the two disengaged) are basically trivial:

```cpp
template <typename T>
auto Optional<T>::operator=(Optional<T> const& rhs) -> Optional<T>& {
    if (has_value_ and rhs.has_value_) {
        // ...
    } else if (has_value_ and not rhs.has_value_) {
        value_.~T();
        has_value_ = false;
    } else if (not has_value_ and rhs.has_value_) {
        ::new (&value_) T(rhs.value_);
        has_value_ = true;
    } else {
        // nothing
    }
    return *this;
}
```

There really isn't much room for choice here - those three cases basically have to do that. Although really we need to use `std::construct_at` instead of placement new, simply because the former is allowed during constant evaluation and the latter is not.

Now, let's handle that first case: what do we do if both sides are engaged?

Well, we could do this:

```cpp
if (this != &rhs) {
    value_.~T();
    ::new (&value_) T(rhs.value_);
}
```

I imagine this isn't what most people were expecting to see. But let's start with the claim that this is _correct_. If our objects already aren't the same (i.e. no need to perform further work), we need to ensure that the two `value_`s have the same value. One way to do that is to destroy ours and then copy-construct over it. If copy construction doesn't give us the "same value," then I don't really know what to say.

Putting this altogether, this implementation looks like:

```cpp
template <typename T>
auto Optional<T>::operator=(Optional<T> const& rhs) -> Optional<T>& {
    if (has_value_ and rhs.has_value_) {
        if (this != &rhs) {
            value_.~T();
            has_value_ = false;
            ::new (&value_) T(rhs.value_);
            has_value_ = true;
        }
    } else if (has_value_ and not rhs.has_value_) {
        value_.~T();
        has_value_ = false;
    } else if (not has_value_ and rhs.has_value_) {
        ::new (&value_) T(rhs.value_);
        has_value_ = true;
    } else {
        // nothing
    }
    return *this;
}
```

This approach is kind of messy and involved and requires some care. But there's something especially interesting about this approach that appears if we rewrite it in a cleaner way:

```cpp
template <typename T>
auto Optional<T>::operator=(Optional<T> const& rhs) -> Optional<T>& {
    if (this != &rhs) {
        if (has_value_) {
            value_.~T();
            has_value_ = false;
        }

        if (rhs.has_value_) {
            ::new (&value_) T(rhs.value_);
            has_value_ = true;
        }
    }
    return *this;
}
```

This is suddenly... pretty clean! Basically: if we need to do anything at all, then we first destroy our value (if we have one) then copy construct the other value (if there is one). Done. Take a minute to convince yourself that this implementation is correct. The two assignments to `has_value_` there are important to ensure that we handle exceptions properly.

There are a couple of valuable aspects to this implementation.

First, it's pretty easy to understand, since we have reduced the states we have to consider significantly. Instead of the cartesian product of the states of the two objects, we actually can consider each one in isolation. This makes it scale very well to more complex types: copy-assignment for `variant<A, B, C>` can be implemented as simply destroy the object you have, then copy construct the object they have (just `3 + 3` states, not `3 * 3` states).

Second, the only type requirement for this operation is copy construction. It does not require copy _assignment_. It's generally nice to have fewer type requirements in your generic code, and there are plenty of types in the world that are copy constructible but not copy assignable.

Importantly, and I really want to stress this, it is not intrinsic to the nature of copy assignment of `Optional<T>` that we invoke the copy assignment of `T`. That is one implementation choice (which I will get to shortly), but it is not the only one.

### Assignment for `Optional<T>` from `T`

At this point, assuming we have a class interface that looks like this:

```cpp
template <typename T>
class Optional {
    union {
        T value_;
    };
    bool has_value_;

public:
    Optional();
    Optional(Optional const&);
    Optional(T const&);
    Optional(T&&);
    auto (Optional<T> const& rhs) -> Optional<T>&;
};
```

Then we actually already support assigning an `Optional<T>` from a `T`. That would invoke the copy assignment operator by way of constructing a temporary using the converting constructor:

```cpp
Optional<int> x(1);

// this
x = 2;

// is equivalent to
x = Optional<int>(2);
```

The semantics of assigning a `T` must be the same as the semantics of assigning an engaged `Optional<T>` which holds that `T`. But this isn't a particularly efficient way to do this: we are copying our value into a temporary `Optional` only to then immediately copy it again into ourselves. This is wasteful. As an optimization (and solely as an optimization), we can provide assignment from `T` that just saves that step. Which otherwise can look the same:

```cpp
auto Optional<T>::operator=(T const& rhs) -> Optional<T> {
    if (&value_ != &rhs) {
        if (has_value_) {
            value_.~T();
            has_value_ = false;
        }

        ::new (&value_) T(rhs);
        has_value_ = true;
    }
    return *this;
}
```

This operator isn't particularly interesting, it solely exists to ensure that `opt = val;` is more efficient than `opt = Optional<T>(val);` but otherwise has identical semantics.

### Copy Assignment for `Optional<T>`, take 2

The implementation I showed earlier is pretty enticing. It's easy to understand, scales well, and has the minimal type requirements. But there's unfortunately one thing wrong with it: performance.

In the case of `Optional<string>` (and other similar types), destroy + copy construct can be quite a wasteful way of doing a copy. If both the source and destination strings were "long" (i.e. their buffers are allocated) and the destination is longer than the source, then assignment could be as cheap as a `memcpy`. But the destroy + copy approach would have to deallocate and then allocate again. That can lead to an enormous amount of overhead for this case.

As a result, a different approach to copy assignment is usually used - deferring to `T`'s copy assignment:

```cpp
template <typename T>
auto Optional<T>::operator=(Optional<T> const& rhs) -> Optional<T>& {
    if (has_value_ and rhs.has_value_) {
        value_ = rhs.value_;
    } else if (has_value_ and not rhs.has_value_) {
        value_.~T();
        has_value_ = false;
    } else if (not has_value_ and rhs.has_value_) {
        ::new (&value_) T(rhs.value_);
        has_value_ = true;
    } else {
        // nothing
    }
    return *this;
}
```

This will perform better for types like `string`. Such types aren't exactly rare (even though copy assignment for `Optional` probably isn't an exceedingly common operation). So it's probably a good tradeoff: we have a more complex implementation with more type requirements (now we do require copy assignment), but we have better performance.

It's tempting to argue that this also has a nice symmetry (implementing `Optional<T>`'s `=` in terms of `T`'s `=`), but we only use that operation in one of the four cases, so it's really not all that symmetric. Moreover, we get a new value of `T` in two different ways here (copy construct or copy assign) whereas in the previous implementation, there was only one.

It bears repeating, though, that while we _can_ implement `Optional<T>`'s copy assignment in terms of `T`'s copy assignment, it is not the case that we _must_ implement `Optional<T>`'s copy assignment this way. It is simply one implementation strategy.

### Copy Assignment for `Optional<T&>`

Of course I was eventually going to have a section about copy assignment for `Optional<T&>`. Now, the implementation strategy I presented for `Optional`'s storage earlier doesn't actually work for `T&` (because you cannot have a reference member of a union, and even if you could you'd certainly implement it as holding a `T*` [anyway]({% post_url 2021-12-13-optional-ref-ptr %})), but it's still useful and informative to consider these strategies as if it were.

Up until now, I have presented two alternative implementation strategies for copy assignment:

1. destroy + copy-construct
2. copy-assign

Where the latter's primary value is that it is an optimization over the former. For most types, these two strategies have the same semantics. But that is _not_ the case for reference types (and proxy references). Let's consider an example:

```cpp
int i = 1;
int j = 2;

Optional<int&> ox;
Optional<int&> oi(i);
Optional<int&> oj(j);

ox = oj;
oi = oj;
```

In both models, `ox = oj` will copy construct the right-hand-side's reference onto the disengaged left-hand-side, ending up with `ox.value_` being a reference to `j`.

But what about `oi = oj`? The copy assignment when the left-hand-side is already engaged?

In the destroy + copy construct implementation, the result of this assignment is that we first destroy the left-hand-side's value (reference) and then copy construct the right hand side's value (reference) onto it. The result of this is that `oi.value_` is now the same reference as `oj.value_` (i.e. `j`) and `i` and `j` remain unchanged. This is usually referred to as _rebinding_ the reference.

In the copy-assign implementation, the result of this operation is syntactically invoking `=`. We do `oi.value_ = oj.value_`. This _assigns through_ the left-hand reference, the result of which is that `oi.value_` is still a reference to `i` but now `i` has the value `2`.

Which is the better choice of implementation? Overwhelmingly destroy + copy construct (i.e. rebinding). For several important reasons.

First, note that in the destroy + copy construct implementation, `ox = oj;` and `oi = oj;` end up doing the same thing. The result is that the left-hand-side is engaged with a reference to `j`. That's a generally important property of assignment - the result should be based on what we're assigning _from_, not what we're assigning _to_. That's decidedly not the case with the copy-assign implementation, where the two different assignments do two very different things.

Second, the copy-assign implementation is valuable as an optimization over the destroy + copy construct implementation. In this case, it does something different, which makes it very much not an optimization anymore. There was no other reason to choose this option to begin with.

Third, even more than that, copy-assignment would actually be a _pessimization_ for the `Optional<T&>` case. `Optional<T&>`'s storage would be a `T*`. The destroy + copy construct algorithm here actually devolves into a defaulted copy assignment operator, and the whole type ends up being trivially copyable. Which is great. But the copy-assign algorithm requires actually having a user-defined assignment operator, making this case no longer trivially copyable. As this type is almost exclusively used as either a parameter or return type, this is a big hit. Using `Optional<T&>`, at least in my experience, is much more common than copy-assigning an `Optional<U>` (for types `U` where copy-assign is more performant than destroy + copy construct).

The only argument to be made in favor the copy-assign implementation for `Optional<T&>`'s copy assignment operator is for consistency - that what `Optional<T>`'s copy assignment operator does is invoke the underlying type's copy assignment, therefore the same should hold for `Optional<T&>`. But as I've noted, this premise doesn't actually hold: there is no such requirement for `Optional<T>`'s copy assignment, so there is no such consistency (and even the copy assignment model doesn't always lead to copy assignment, only sometimes).

This argument isn't especially close.

Another interesting argument to consider is generalizing out from `Optional<T&>` to `Variant`. What should this do:

```cpp
int i = 1;
float f = 3.14;

Variant<int&, float&> va = i;
Variant<int&, float&> vb = f;

va = vb; // ???
```

Now, this should obviously change `va` such that it is holding an `float&` referring to `f`. But is it really that obvious? With the destroy + copy-construct model, this clearly follows. But with copy-assign, well... couldn't this effectively do `i = j;`? After all, we're deferring syntactically to whatever `=` does. But it doesn't because the copy-assign part of the copy-assign model really only happens in the case where the source and destination are holding the same index (note: not just same type, since `Variant` might have multiple different states of the same type), which is part of what makes the copy-assign model more complex than might appear at first glance.

### Assignment for `Optional<T&>` from `T&`

As with the [same case for `Optional<T>`](#assignment-for-optionalt-from-t), assigning to an `Optional<T&>` from a `T&` must do the same thing as assigning to it from an `Optional<T&>` engaged with that particular `T&`. In this case, we don't have to worry about the pessimization of the extra `Optional` construction, so an implementation need not even provide this operator.

One common mistake I see in discussion about this topic is the misbelief that there is a difference between the assignment operators of `Optional<T&>` from `Optional<T&>` and from `T&` (e.g. `Optional<T&>`'s copy assignment operator should assign through the reference, but it's assignment from `T&` should be deleted), but there cannot be. Any such difference would be a glaring inconsistency in the semantics between the two operations.

### Copy Assignment for `Optional<tuple<T&>>`

At this point, it's clear that copy assignment for `Optional<T&>` must rebind the underlying reference, while copy assignment for `Optional<string>` _should_ copy-assign the underlying `string` (although it _could_ also destroy + copy construct). One way to generalize this is to use the copy-assign implementation for all types, but to use the destroy + copy construct implementation for language references, specifically (which has the added benefit of making `Optional<T&>` trivially copyable).

This is what `boost::optional` does. It is also what my `Optional` implementation does (not a coincidence). This choice gives you the efficient implementation for types like `string` and the desired, semantically-sound implementation for `T&`.

Here's where things really get fun (or, depending on perspective, go off the rails): what should we do for `Optional<tuple<T&>>`?

`tuple<T&>` isn't `T&`, so these implementations (`boost` and my own) fall back to copy-assign. But copy-assign for `tuple<T&>` _itself_ does copy-assign internally! This means we have the exact same problem all over again:

```cpp
int i = 1;
int j = 2;

Optional<std::tuple<int&>> ox;
Optional<std::tuple<int&>> oi(i);
Optional<std::tuple<int&>> oj(j);

// ox now holds a tuple<int&> which refers to i
ox = oj;

// oi's tuple<int&> still refers to i, not j
// instead, this assigns i = 2
oi = oj;
```

Here, `tuple<T&>`'s assignment does assign-through very much by design: it is a proxy reference type. But `Optional<T>` isn't trying to be a proxy reference type and it certainly isn't trying to _conditionally_ be a proxy reference type (i.e. it's a proxy reference only when engaged). Such behavior is definitely not desired.

The problem boils down to what `x = y;` even means, and the fact that it actually in C++ can mean two very different things:

1. Change the value of `x` to be the same as `y` (i.e. `x` is a value type)
2. Change the value to which `x` refers to be the same as `y` (i.e. `x` is a language reference or a proxy reference)

For `T*`, we have distinct syntax for these cases: `p = q;` or `*p = r;`, but for `T&` we don't (indeed language references don't even support rebinding) [^ref].

[^ref]: One interesting thing in Rust is that Rust references (`&T`) behave mostly like C++ pointers: they're rebindable and assigning through them requires explicit dereferencing. However, Rust also has implicit dereferencing to avoid a lot of the tedious cases - instead of writing `*r1 == *r2` you can just write `r1 == r2` (and if you really want to compare the references themselves for equality, you have to write `std::ptr::eq(r1, r2)`, which coerces the references to pointers). I can't say that I really understand the implicit dereference rules, but I can say that at least Rust avoids this problem of the two distinct meanings of `=`.

So how do we fix it?

We could try to detect such cases. C++20 even comes with a relevant concept for this: `indirectly_writable<Out, T>` (which tries to detect references and proxy references by way of checking `const`-assignability: [\[iterator.concept.writable\]](http://eel.is/c++draft/iterator.concept.writable)). We could take a page out of that book:

```cpp
template <class T>
concept proxy_reference_copy = requires (T a, T const c) {
    a = c;
    c = c;
};
```

That holds for `int&`, not for `int`, but will hold for `std::tuple<int&>` (as a result of the `zip` paper, [P2321](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p2321r2.html)). But it won't hold for `boost::tuple<int&>`, unless boost's implementation changes, or any other similar type.

This kind of opt-in is okay for the `zip` world (where types need to make changes to enable functionality), but probably not great for `Optional` assignment (where types need to make changes to transition from meaningless to meaningful functionality).

A second approach might be to do destroy + copy-construct by default, and provide a trait to opt into copy-assign. Maybe something like this:

```cpp
template <class T>
inline constexpr bool optional_copy_assign = false;

template <>
inline constexpr bool optional_copy_assign<std::string> = true;

template <class T>
inline constexpr bool optional_copy_assign<std::vector<T>> =
    optional_copy_assign<T>;

template <class T, class U>
inline constexpr bool optional_copy_assign<std::pair<T, U>> =
    optional_copy_assign<T> and optional_copy_assign<U>;

template <class... T>
inline constexpr bool optional_copy_assign<std::tuple<T...>> =
    (optional_copy_assign<T> and ...);

// ... etc. ...
```

This approach is safe, in the sense that the only types that would use copy-assign would be the ones that explicitly opted in to such support. But there are very, very, very many such types. This just seems _incredibly_ tedious. This problem isn't particularly unique to `Optional` either. It's somewhat general to any wrapper type.

A third approach might be: forget it. Just unconditionally do destroy + copy-construct for all types. Including `Optional<string>`. Sure, we pessimize copy-assignment compared to the theoretical best. But we have a simple design that is definitely semantically correct for all types, and that is very important. How significant is copy-assignment anyway? Note that move-assignment, even in the destroy + copy-construct model, is still fine. Is the added benefit of improved performance sufficient for the added complexity of having to have an opt-in trait to get that performance (or the added pain of having some types having the wrong semantics)?

A fourth approach might be: forget it, just differently. As in, delete copy assignment. I'm not sure that this is necessarily better than simply unconditional destroy + copy construct. You avoid some operations being more expensive than you might expect, but then some operations just don't work when you'd expect them to. Not sure it's necessarily the right trade-off.


### Conclusion

There are two ways to implement copy assignment for `Optional<T>`:

1. destroy + copy-construct
2. copy-assign

destroy + copy-construct is a simpler design that is definitely semantically correct for all types.

copy-assign is more performant (potentially significantly so) for some types (e.g. `std::string`), equivalent for some types (e.g. trivially copyable ones), and semantically wrong for other types (e.g. references and proxy references). In no uncertain terms: a copy-assign implementation for `Optional<T&>` is wrong.

For `Optional<T&>`, implementations can simply account for this by providing a custom implementation that both implements `Optional<T&>` as a `T*` and also provides for rebinding assignment. But for `Optional<tuple<T&>>`, implementations can't realistically special case this. There are fewer proxy reference types than regular types, but still quite a lot of them. And, besides, what do you do for `Optional<tuple<T&, U>>` [^tuple]?

[^tuple]: You'd have to destroy + copy-construct such cases, unless you really go wild and try to handle each part of the `tuple` separately? This is the case which really breaks the `proxy_reference_copy` idea, since `std::tuple<U...>` is only const-assignable if _all_ the `U`s are, but we'd need to fall-back to destroy + copy-construct if _any_ of the `U`s are reference-like.

This means that there are, I think, only two viable approaches to implementing `Optional`:

1. Just special-case `Optional<T&>`, leaving `Optional<tuple<T&>>` to have incorrect semantics, but under the premise that assignment is rare for such a type anyway so it's probably not that big a deal.
2. Always do destroy + copy-construct.

The second approach is more sound, consistent, and probably just better overall, although I'm not sure if there is an implementation that does it. `std::optional` for sure could not change to do that. Somebody, somewhere, is copy-assigning one engaged `std::optional<std::tuple<T&>>` to another and relying on the current assign-through behavior [^break].

But the first approach is still definitely an... option! You'll have some types whose copy assignment is wrong (although we could make the check sufficiently complex as to do the right thing for `std::pair` and `std::tuple`), but it's the least inconsistent option available. An `Optional<T&>` whose copy assignment assigns through the reference would be quite bad. An `Optional<T&>` whose copy assignment is deleted is just differently inconsistent in a way that strikes me as gratuitous. But special casing `Optional<T&>` to rebind (even if `Optional<tuple<T&>>` remains unfortunately broken) still provides value - so it's something we should consider.

---

[^break]: How would you even determine whether this is true?
