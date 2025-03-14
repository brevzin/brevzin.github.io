---
layout: post
title: "Polymorphic, Defaulted Equality"
category: c++
tags:
 - c++
 - c++20
---

I recently ran into an interesting bug that I thought was worth sharing.

## The Setup

We have an abstract base class, with polymorphic equality:

```cpp
struct Base {
    virtual ~Base() = default;
    virtual auto operator==(Base const&) const -> bool = 0;
};
```

And then we have a bunch of derived classes from this abstract base that implement equality in the expected way. If the two objects are the same type, downcast them and then do member-wise comparison:

```cpp
struct Derived : Base {
    int m1;
    int m2;
    // ...

    auto operator==(Base const& rhs) const -> bool override {
        if (typeid(rhs) == typeid(Derived)) {
            return *this == static_cast<Derived const&>(p);
        } else {
            return false;
        }
    }

    auto operator==(Derived const& rhs) const -> bool = default;
};
```

> The initial version of this blog did the type check by doing `dynamic_cast<Derived const*>(&rhs)`:
> ```cpp
> if (auto p = dynamic_cast<Derived const*>(&rhs)) {
>     return *this == *p;
> } else {
>     return false;
> }
> ```
> That's not what our actual code did, was just a simplification for the blog. But that's incorrect in the presence of more-derived types.
> ```cpp
> struct Derived : Base { /* ... */};
> struct SuperDerived : Derived { /* ... */ };
>
> Base* d = new Derived( /* ... */);
> Base* sd = new SuperDerived( /* ... */ );
> *d == *sd; // dynamic_cast<Derived const*> succeeds, so might return true
> *sd == *d; // dynamic_cast<SuperDerived const*> fails, so definitely false
> ```
> The `typeid` check ensures the types do match.
{:.prompt-info}


The `override` can be easily implemented as a function template, call it `return polymorphic_equality(*this, rhs)`, to avoid that duplication:

```cpp
template <class D>
auto polymorphic_equality(D const& lhs, Base const& rhs) -> bool {
    if (typeid(rhs) == typeid(D)) {
        return lhs == static_cast<D const&>(rhs)
    } else {
        return false;
    }
}
```

 We wanted to compare all the members without having to manually write them out (and potentially forget one), so defaulting equality lets us do just that. Seems pretty nice!

There's just one problem with it.

It doesn't work.

## The Issue

So it turns out, when you actually use the above code to do comparisons, you'll hit a stack overflow. And it took me a while to figure out why that was the case, even once I narrowed down the issue to `operator==`. Some of you may have already spotted the issue in the above reduction, but it's definitely not obvious.

What does _defaulting_ `operator==` mean? Usually people (and I am guilty of this as well) talk about it as giving you the default, member-wise comparison, saving you the time (and error) of writing out all of those by hand. But that's not exactly right. Defaulted equality doesn't give you _member-wise_ comparisons, it gives you _subobject-wise_ comparisons.

That is, for the above example, the compiler doesn't generate this (which is our desired behavior):

```cpp
auto Derived::operator==(Derived const& rhs) const -> bool {
    return m1 == rhs.m1
       and m2 == rhs.m2;
}
```

It generates _this_:

```cpp
auto Derived::operator==(Derived const& rhs) const -> bool {
    return static_cast<Base const&>(*this) == static_cast<Base const&>(rhs)
       and m1 == rhs.m1
       and m2 == rhs.m2;
}
```

And so now the problem is more clear. What does comparing our `Base` subobjects actually do?

Well, that is going to do virtual dispatch to call `Derived::operator==(Base const&) const`, which is going to do another `dynamic_cast` to get us back down to... oh yeah, recursing into `Derived::operator==(Derived const&) const`. Infinitely recursively. Because we compare the `Base` first, we don't even get the opportunity to fail if the members don't line up. Do not pass Go, do not collect $200, go directly to ~~jail~~ stack overflow.

That... sucks.

## The Solution

So what do we actually do about this? Well, we wanted `Base`s to be equality comparable for convenience. And once we get down to the `Derived`, that comparison _should_ be member-wise. But there's just no convenient mechanism to do _both_ of these things at the same time.

If we wanted to spell `Base`'s comparison differently, no problem, defaulting works great:

```cpp
struct Base {
    virtual ~Base() = default;
    virtual auto equals(Base const&) const -> bool = 0;
    auto operator==(Base const&) const -> bool = default;
};

struct Derived : Base {
    int m1;
    int m2;
    // ...

    auto equals(Base const& rhs) const -> bool override {
        return polymorphic_equality(*this, rhs);
    }

    auto operator==(Derived const& rhs) const -> bool = default;
};
```
{: data-line="3,4,16" .line-numbers }

We had to add an extra, defaulted comparison to `Base`, because we are still doing subobject-wise comparison — but now this no longer leads to infinite recursion. Neither via `==` nor via `equals`. So that's a solution, that loses some convenience.

Another solution is to actually wrap `Derived`'s members in another type that locally has defaulted equality. This is more (potentially, much more) tedious to implement all the rest of `Derived`, but at least means that we don't have to manually write the comparison:

```cpp
struct Base {
    virtual ~Base() = default;
    virtual auto operator==(Base const&) const -> bool = 0;
};

struct Derived : Base {
    struct Members {
        int m1;
        int m2;
        // ...

        auto operator==(Members const&) const -> bool = default;
    };
    Members m;

    auto operator==(Base const& rhs) const -> bool override {
        return polymorphic_equality(*this, rhs);
    }

    auto operator==(Derived const& rhs) const -> bool {
        return m == rhs.m;
    }
};
```
{: data-line="12,20-22" .line-numbers }

Another solution, with reflection, is that we can actually easily implement member-wise equality ourselves:

```cpp
template <class T>
constexpr auto memberwise_eq(T const& lhs, T const& rhs) -> bool {
    constexpr auto ctx = std::meta::access_context::unchecked();
    template for (constexpr auto m : define_static_array(
                                        nonstatic_data_members_of(
                                            ^^T, ctx)))
    {
        if (not (lhs.[:m:] == rhs.[:m:])) {
            return false;
        }
    }
    return true;
}
```
{: .line-numbers }

The spelling to get all (including private) the non-static data members is pretty verbose, since we both need provide an `access_context` (see [P3547](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2025/p3547r0.html)) and then since we need this to be a `constexpr` variable and we don't have non-transient allocation, we need to promote this to static storage ourselves (see [P3591](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2025/p3491r1.html)). But that is what it is, it can be wrapped. Point is, outside of that, it's a fairly straightforward function template.

And once we have that, we can just directly write (actually) member-wise comparison:

```cpp
struct Base {
    virtual ~Base() = default;
    virtual auto operator==(Base const&) const -> bool = 0;
};

struct Derived : Base {
    int m1;
    int m2;
    // ...

    auto operator==(Base const& rhs) const -> bool override {
        return polymorphic_equality(*this, rhs);
    }

    auto operator==(Derived const& rhs) const -> bool {
        return memberwise_eq(*this, rhs);
    }
};
```
{: data-line="15-17" .line-numbers }

## The Conclusion

Of these, the reflection solution is my favorite, simply because it lets me actually have the interface I want — `Base` has an `==` (not `equals`) and I am directly expressing my intent. It's just unfortunate the language feature we have to solve this problem ... doesn't. And that's not a knock on defaulted `==` equality. I don't think it would make sense to live in a world where you could default `==` but that _didn't_ compare the base class subobjects. After all, defaulting your copy constructor does actually copy your base class subobjects too. Would be pretty weird if it didn't!

And maybe the real problem is that the desire for `Base` to have an `==` is wrong to begin with, and so the infinite recursion we ran into is downstream of that initial bad design decision. Not sure.

But no matter what, I thought it was an interesting bug that was worth sharing. Hope you agree.