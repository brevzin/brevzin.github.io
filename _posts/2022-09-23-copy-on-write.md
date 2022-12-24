---
layout: post
title: "Copy-on-write with Deducing <code class=\"language-cpp\">this</code>"
category: c++
tags:
  - c++
  - c++23
---

One of the new language features for C++23 is [Deducing `this`](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p0847r7.html), which is a feature I co-authored with Gašper Ažman, Sy Brand, and Ben Deane. The interesting history there is that Sy and I were working on solving one problem (deduplication of all the `const` and ref-qualifier overloads) and Gašper and Ben were working on another (forwarding lambdas) and it just so happened that Jonathan Wakely pointed out that we were converging on a similar solution.

In short, the facility allows you to declare an _explicit_ object parameter (whereas C++ has always let you have an _implicit_ object parameter, that `this` points to), which is annotated with the keyword `this`. And... that's basically the whole feature - this new function parameter behaves the same as any other kind of function parameter, and all the other rules basically follow from that. Ben gave a [whole talk](https://www.youtube.com/watch?v=jXf--bazhJw) on this at CppCon 2021, and Timur Doumler used this feature as one of the four he talked about in this keynote at CppCon 2022 on how C++23 will change how we write code (I'll post the link when it becomes available).

What makes me most excited about this language feature is that the design we ended up with is a fairly simple one that nevertheless solves a variety of completely unrelated problems. Indeed, a lot of the use-cases we're aware of were not use-cases that we explicitly set out to solve - they're just ones that we discovered along the way. Recursive lambdas? Discovered. A better approach to CRTP and builder interfaces? Discovered. Who knows how many other interesting things people will come up with built on this one simple feature.

So I thought I'd write a new post about a use-case for deducing `this` that I just thought of last week: implementing copy-on-write.

## Copy-on-Write

Copy-on-Write (or, COW, because people love their acronyms) is a strategy to make copies cheaper by deferring actually making the copy until you actually need one. Basically, if you're not going to mutate your value, you can't really tell if the value you have to distinct or not, so copy-on-write is an approach to allow for greater use of value semantics. The nice thing is that "copies" become cheaper (O(1) really) and you don't have to use references as much. The downside is that you can have surprising and unpredictable performance costs when that copy actually occurs. Plus, everything kinds of needs to go on the heap.

But my goal isn't really to talk about why Copy-on-Write is a good idea or a bad idea. Let's talk about how to implement it.

If I had wanted to write a regular `Vector<T>`, I'd have something like this (obviously there's more to `Vector<T>` than this, but this is good enough for demonstration purposes)

```cpp
template <class T>
class Vector {
    T* begin_;
    T* end_;
    T* capacity_;

public:
    // copy constructor always allocates
    Vector(Vector const& rhs) {
        begin_ = ::operator new(
            sizeof(T) * (rhs.capacity()),
            std::align_val_t{alignof(T)});
        end_ = std::uninitialized_copy(
            rhs.begin_, rhs.end_, begin_);
        capacity_ = begin_ + rhs.capacity();
    }

    // and the mutable and const accessors do the same thing
    auto operator[](size_t idx) -> T& {
        return begin_[idx];
    }

    auto operator[](size_t idx) const -> T const& {
        return begin_[idx];
    }
};
```

If I wanted to write a copy-on-write `Vector<T>`, things would look a bit different. I'd need a reference count that I'd need to allocate. So I might as well just put more stuff in the allocation. And then the mutable case looks quite different:

```cpp
template <class T>
class CowVector {
    struct State {
        std::atomic<int> ref;
        size_t size;
        size_t capacity;

        T elements[];
    }
    State* state;

    // if we're not unique, we need to allocate
    // a new State and copy the elements.
    // if we are unique, this is a no-op.
    void copy_on_write();

public:
    // copy constructor *never* allocates.
    // just increments ref-count
    CowVector(CowVector const& rhs)
        : state(rhs.state)
    {
        ++state->ref;
    }

    // and the mutable and const accessors do different things
    auto operator[](size_t idx) -> T& {
        copy_on_write();
        return state->elements[idx];
    }

    auto operator[](size_t idx) const -> T const& {
        return state->elements[idx];
    }
};
```

Importantly, _every_ mutable has to remember to call `copy_on_write()` first. Otherwise, we end up mutating shared state, and now our copies aren't copies anymore. This isn't overly difficult to do, but you do have to remember to do it. But also to not go crazy calling it too many times - while the function is idempotent, and fairly cheap after the first time, it is still totally unnecessary work. It's always better to do less work.

So... can we do better?

## The Explicit Object Parameter

The simplest example with deducing `this` is to just take an existing set of member functions and just demonstrate what they look like using the new syntax in a way that's still equivalent. For instance:

```cpp
template <class T>
class CowVector {
public:
    auto operator[](size_t idx) -> T&;
    auto operator[](size_t idx) const -> T const&;
};
```

Becomes:

```cpp
template <class T>
class CowVector {
public:
    auto operator[](this CowVector& self, size_t idx) -> T&;
    auto operator[](this CowVector const& self, size_t idx) -> T const&;
};
```

This, in of itself, isn't super useful - it doesn't let us do anything we couldn't do before, although some people might prefer the latter syntax stylistically. Usually the next step is then to illustrate that once the object parameter is actually a parameter, it can become a template:

```cpp
template <class T>
class CowVector {
public:
    template <class Self>
    auto operator[](this Self& self, size_t idx)
        -> std::copy_const_t<Self, T>&
    {
        if constexpr (not std::is_const_v<Self>) {
            self.copy_on_write();
        }
        return self.state->elements[idx];
    }
};
```

In some contexts, this is quite useful, since it can reduce overload sets in a way that reduces code duplication and makes them easier to implement and understand. [The paper](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p0847r7.html) has some nice examples of this.

But in this _particular_ case, it's kind of a step backwards? Our two overloads don't actually do the same thing, and the conditional copy-on-write call isn't really the best. It could be improved a bit:

```cpp
template <class T>
class CowVector {
    struct State { ... };
    State* state;

    // this one (potentially) copies
    auto get_state() -> State*;

    // this one doesn't, because const
    auto get_state() const -> State const* { return state; }
public:
    template <class Self>
    auto operator[](this Self& self, size_t idx)
        -> std::copy_const_t<Self, T>&
    {
        return self.get_state()->elements[idx];
    }
};
```

But I'm not sure this is any better either - since it's pretty nice to visually see the potential copy happen in the code and now we don't have that at all. So uh, where am I going with this again?

Well, it turns out there's something else you can stick in the explicit object parameter other than just an explicit reference to the class type or a deduced parameter: a different type entirely.

## An Explicit Object Parameter of Differing Type

Consider:

```cpp
struct X {
    int i;
    constexpr operator int() const { return i; }
    constexpr auto plus(this int x, int y) -> int { return x + y; }
};

static_assert(X{1}.plus(2) == 3);
```

Here, we have an explicit object parameter of type... `int`? That's weird, but remember that the explicit object parameter is _just a parameter_. Our type, `X`, is convertible to `int`, so this works just fine. We thought about rejecting it at some point, or trying to figure out how to add restrictions on the explicit object parameter that its type had to be `X` or some kind of reference to `X`. But... why?

At the time we didn't really have any particular reason to want to allow this, but we also didn't have any particular reason to reject it either - it's non-trivial to figure out how to reject, and also felt kind of like an arbitrary restriction. After all, it's just a parameter right?

The interesting thing about allowing a different kind of parameter, though, is that it provides a means to decorate a function. For instance, we know for copy-on-write that mutable functions need to operate on enforced-unique state and const functions shouldn't do anything. We can enforce that at signature level:

```cpp
template <class T>
class CowVector {
    struct State {
        std::atomic<int> ref;
        size_t size;
        size_t capacity;

        T elements[];
    }
    State* state;

    // if we're not unique, we need to allocate
    // a new State and copy the elements.
    // if we are unique, this is a no-op.
    void copy_on_write();

    struct ImmutableState {
        State* state;
        auto operator->() -> State* { return state; }
    };
    struct MutableState : ImmutableState { };

public:
    // the MutableState conversion ensures that
    // we have unique, mutable state
    operator MutableState() {
        copy_on_write();
        return MutableState{state};
    }

    // whereas the ImmutableState conversion is
    // just a thin wrapper that is a no-op
    operator ImmutableState() const {
        return ImmutableState{state};
    }

    auto operator[](this MutableState state, int i) -> T& {
        return state->elements[i];
    }

    auto operator[](this ImmutableState state, int i) -> T const& {
        return state->elements[i];
    }
};
```

What's going on here?

If we have a situation like:

```cpp
auto f(CowVector<int> const& v) -> int const& {
    return v[1];
}
```

Then name lookup will find the two `operator[]`s. The mutable one isn't a viable candidate since we don't have a conversion sequence to get from a `CowVector<int> const` to a `MutableState` (that conversion function is mutable), but we do to get from a `CowVector<int> const` to an `ImmutableState`. So we do that conversion (which just copies our `State` pointer) and return the appropriate element.

But if we have a situation like:

```cpp
auto g(CowVector<int>& v) -> int& {
    return v[1];
}
```

Then we have three options:

1. we can convert `v` to a `MutableState` and call `operator[](MutableState, int)`
2. we can convert `v` to a `MutableState` and call `operator[](ImmutableState, int)`
3. we can convert `v` to an `ImmutableState` and call `operator[](ImmutableState, int)`

Of these, (1) is the best. It's intuitively the best (we don't have to convert `v` to `const` to call the conversion function, and it's the most derived resulting type), although I'm not even sure that we have a clear rule to prefer (1) to (3) (somehow the fact that `MutableState` derives from `ImmutableState` is relevant).

When we undergo the conversion from `CowVector<int>` to `CowVector<int>::MutableState`, the (potential) copy-on-write happens at that point.

And that's that. Basically our approach to implementing `CowVector` is that const functions take a `ImmutableState` object parameter and mutable functions take a `MutableState` object parameter. All the interesting mutating functions (`reserve`, `push_back`, etc.) can be added as members onto `MutableState` for convenient use - and none of those functions need to check the reference count, since we know we have a unique, mutable reference at that point.

You can't forget a call to `copy_on_write`, since that will happen by virtue of how all the member functions are declared.

You can play around with this implementation [here](https://godbolt.org/z/65jj79o8x).

### Conclusion

Deducing `this` is a pretty cool language feature, with use-cases that I'm sure we'll continue to keep discovering over time. Like this implementation strategy for copy-on-write! Or, more generally, a limited ability to decorate the object parameter on member functions.

It may not be the most compelling use-case of this facility, but I thought it was pretty cute.

### Real Conclusion

... but actually, this is a terrible implementation of copy-on-write. As Dave Abrahams pointed out to me, assuming that you need to make a full copy just because you're not unique is a huge pessimization.

Consider, for instance, `clear()`. The efficient thing to do is:

```cpp
template <class T>
void CowVector<T>::clear() {
    if (state_->is_unique()) {
        // mutate state in place
    } else {
        // allocate new empty state
    }
}
```

Importantly, we allocate a new _empty_ state. We do not need to first copy arbitrarily many elements just to then destroy all the copies because we didn't need them to begin with. The implementation I'm demonstrating here would do that. Needless to say, that's suboptimal.

Moreover it's not just that `clear()` is a special case either. Consider `v.push_back(x)`. If `v` isn't unique, we don't want to just copy our state (allocating space for `v.capacity()` elements) - if we're at capacity, that means we'd have to first allocate (and copy) `v.capacity()` elements and then immediately grow, allocating `v.capacity() * 2` elements and copying again. We'd want to be smarter - allocating space for at least `v.size() + 1` elements, so that we only do a single allocation.

So while this was a cute approach to this problem, and there probably is a good use-case out there for using explicit object parameters with a different type, this ain't it.
