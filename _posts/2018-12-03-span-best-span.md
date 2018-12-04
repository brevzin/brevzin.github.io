---
layout: post
title: "span: the best span"
category: c++
tags:
 - c++
 - c++20
 - span
--- 

This post is a response to [RangeOf: A better span](https://cor3ntin.github.io/posts/rangeof/), which has many problems worth addressing in detail. While most of this post will deal with specifically `std::span<T>`{:.language-cpp} (which is indeed the best `span`{:.language-cpp}), the last section will also discuss a recent addition to the standard library: `std::ranges::subrange<T*>`{:.language-cpp}.

### Non-issues

The original post presents three "issues" with `span`. One is about naming - but naming is hard and people can disagree as to what the right name for such a thing could be. `span` seems fine to me. In my code base at work, we call it `Slice<T>`{:.language-cpp} (named after Rust's concept of the same name), though this name wouldn't work so well in C++ since there already is a thing in the standard library called [`std::slice<T>`{:.language-cpp}](https://en.cppreference.com/w/cpp/numeric/valarray/slice). The third is about how `span` can only be used over contiguous memory, which is why it exists - so I have trouble seeing a problem in that the type does not solve a problem that it wasn't trying to solve. 

The second listed issue is worth discussing in more detail. It says:

- Being non-owning, it’s a view in the Range terminology. Its constness is _shallow_. that means that you can modify the underlying element of a `const span`{:.language-cpp}

But far from being an issue, shallow `const`{:.language-cpp}-ness is the only reasonable implementation choice for this type, and it's worth understading why. `span` is a view, or more generally it is a reference-like type. It simply refers to data, it doesn't own it. Copying a `span` is cheap - it's just copying a couple pointers - and each copy also refers to the same underlying data. What this means is that, were `span` to propagate `const`{:.language-cpp}, it would be very easy to get around:

```cpp
std::vector<int> v = {1, 2, 3};

std::span<int> const a = v;
// even if this did not compile...
a[0] = 42;

// ... this surely would
std::span<int> b = a;
b[0] = 42;
```

Since we can so easily "remove" the `const`{:.language-cpp} by doing a cheap copy, it doesn't really make sense to prevent non-`const`{:.language-cpp} access. This follows the core language rules for reference-like types that we're more familiar with: pointers do not propagate top-level `const`{:.language-cpp} - you can modify the element that a `T* const`{:.language-cpp} points to.

We also see this in the specification for the [`View` concept](http://eel.is/c++draft/range.view) in Ranges:

```cpp
template<class T>
  concept View =
    Range<T> && Semiregular<T> && enable_view<T>;
```

where the default value of `enable_view<T>`{:.language-cpp} is based on part on: "Otherwise, if both `T`{:.language-cpp} and `const T`{:.language-cpp} model `Range`{:.language-cpp} and `iter_reference_t<iterator_t<T>>`{:.language-cpp} is not the same type as `iter_reference_t<iterator_t<const T>>`{:.language-cpp}, `false`{:.language-cpp}. [ Note: Deep const-ness implies element ownership, whereas shallow const-ness implies reference semantics. — end note ]". In other words, if a `Range`{:.language-cpp} has deep const-ness, it is _not_ a `View`{:.language-cpp}.

### `span<T>`{:.language-cpp} vs `ContiguousRange auto const&`{:.language-cpp}

The bulk of the original post suggests replacing functions taking parameters of type `span<T>`{:.language-cpp} with function templates taking parameters constrained by `ContiguousRange`{:.language-cpp}. That is, to replace:

```cpp
template <typename T>
void f(const std::span<const T> & r);
```
with
```cpp
void g(const std::ContiguousRange auto & r);
```

Let's start with `f`. First of all, you basically never want to take a `span` by reference to `const`{:.language-cpp}. Types like `span` are cheap to copy - so you're not saving anything by taking a reference. You are however introducing another indirection as well as the possibility of aliasing that you don't need. The only exception is if you really do need the _identity_ of the `span` in question (e.g. if you're using one as an out parameter). That's probably not the case here, so pass by value. 

Secondly, it is quite rare to want to _deduce_ the underlying value type of a `span`, in the same way that it is rare to deduce the underlying signature of a `std::function`{:.language-cpp}. The advantage of type erasure is the ability to work seamlessly with a wide variety of objects that meet the right set of requirements - if we deduce the value type of `span`, we can _only_ work with `span`. You can't pass in a `vector<int>`{:.language-cpp} to `f` - that is, unless you explicitly write `f<int>(some_vector)`{:.language-cpp}, and that's just unfriendly. You would almost always write a concrete type instead. 

There is a similar problem with `g` in this regard, in that it's very difficult to actually get the value type from the constrained template argument - there's just no easy way to do that with Concepts today. I have a whole post about such [Concepts declarations issues]({% post_url 2018-10-20-concepts-declarations %}).

So let's just pick a value type instead - let's say, `int`{:.language-cpp}. That gets us to:

```cpp
void f(std::span<int const>);
// versus
void g(ContiguousRangeOf<int const> auto const&);
```

Alright, let's talk about `g` now. What actually does that signature mean? Let's just expand it out to use the most verbose possible syntax for added clarity and see what happens when we call these functions:

```cpp
void f(std::span<int const>);

template <typename R>
    requires ContiguousRange<R> &&
       Same<iter_value_t<iterator_t<R>>, int const>
void g(R const&);

std::vector<int> v = {1, 2, 3};
std::vector<int> const& cv = v;

f(v);  // ok
f(cv); // ok
g(v);  // error
g(cv); // error
```

What happened?

A `span<int const>`{:.language-cpp} is very flexible, it can accept `v` or `cv` just fine. But the constraint we're putting on the range says that `iter_value_t` must be `int const`{:.language-cpp}. But the `value_type`{:.language-cpp} for both `vector<int>::iterator`{:.language-cpp} and `vector<int>::const_iterator`{:.language-cpp} is just `int`{:.language-cpp} (and indeed the `value_type`{:.language-cpp} should never be cv-qualified). No match. 

Can we fix this? We can try to swap from using `value_type` to using `reference`, since that would let you distinguish the two different iterator types. If we're careful enough about references, that gets us a little bit closer:

```cpp
template <typename R, typename V>
concept ContiguousRangeOf = ContiguousRange<R> &&
    Same<iter_reference_t<iterator_t<R>>, V&>;

void g(ContiguousRangeOf<int const> auto const&);

g(v);  // error: int& isn't int const&
g(cv); // error: same
```

Oh right, in both cases we're deducing `std::vector<int>`{:.language-cpp}, even though `cv`{:.language-cpp} is a reference to `const`{:.language-cpp}. We'd need to switch to:

```cpp
void g(ContiguousRangeOf<int const> auto&&);

g(v);  // error: int& isn't int const&
g(cv); // ok
```

There's probably some way of specifying this concept to allow precisely the right things in the `const`{:.language-cpp} access case... but it escapes me at the moment. At least, I mean some way other than `ConvertibleTo<span<int const>>`{:.language-cpp}, which seems to defeat the purpose. But let's just use that for now since it works:

```cpp
void g(ConvertibleTo<span<int const>> auto&& r) {
    r[0] = 42;
}

g(v); // perfectly okay: assigns v[0] to 42
```

We want to express that we only want read-only access to the elements - we said `int const`{:.language-cpp} and not `int`{:.language-cpp} - but we can't actually enforce that in the body. I can pass in a non-const `vector` and then modify its elements just fine. There is nothing stopping me. As a result, there's very little semantic information that you can deduce from the signature of `g` compared to the signature of `f` - `f` is _much_ more expressive. 

One way to solve this particular subproblem is to have a concept that checks the `value_type` and one that checks the `reference`. That is, take a `ContiguousRangeWithValue<int> auto const&`{:.language-cpp} for the const case and a `ContiguousRangeWithReference<int> auto&&`{:.language-cpp} for the non-const case. This would, I think, work and do the right thing - but it is both quite complex and the difference between these cases is really subtle and beginner-hostile.

Let's assume that we come up with the correct `ContiguousRangeOf` concept that checks the right things for us. That still doesn't mean that this version is easy to use. Consider some simple function that just wants to assign one element:

```cpp
void f(span<int> s) [[expects: !s.empty()]] {
    s.front() = 42;
}

void g(ContiguousRangeOf<int> auto&& r) [[expects: !r.empty()]]  {
    r.front() = 42;
}

std::vector<int> v = {1, 2, 3};
f(v); // ok
g(v); // ok

int arr[] = {1, 2, 3};
f(arr); // ok
g(arr); // err
```

Raw arrays don't have member functions. Our constraint just requires that the range is contiguous - it says nothing at all about whether that range has member functions named `empty` or `front`. So even if you can come up with the right way to constrain these functions, you still have to be exceedingly careful about the implementation of them. 

On top of all of this, the example in the original post and the one I've been using - `void f(span<int const>)`{:.language-cpp} is just one single function, but whatever the right function template ends up being for this scenario would end up with many, many instantiations - for every kind of range, for every value category and constness. Not only does this bloat compile times, it also just increases the amount of code that needs to be emitted - which would hurt instruction cache. 

Typically, when we consider the trade-offs between using type erasure and using templates, we talk about things like convenience, compilation time, and the ability to use heterogeneous types as benefits for type erasure whereas the benefit for using templates is performance. Type erasure typically performs worse because we have to rely on either allocation (to create the type erased object), indirect dispatch via `virtual`{:.language-cpp} functions or function pointers (to provide a common interface), or both. Indeed, the performance hit on type erasure can be quite large! So, surely, when performance matters, we would want to use `ContiguousRangeOf<int> auto&&`{:.language-cpp}? Actually, `span` is special in this regard. There is never any allocation necessary and there is no indirection. The only overhead on using `span<int>`{:.language-cpp} directly instead of `vector<int>&`{:.language-cpp} is the overhead of constructing the `span<int>`{:.language-cpp} itself. And it might even be better than that, due to being able to take the `span` by value - which means we don't have to keep going to memory to look up our data. Even on the front that type erasure typically loses, `span` does just fine.

To summarize:
- The solution presented in the original post is not a solution at all. Fixing it is non-trivial, and you have to be careful to ensure that you use forwarding references - otherwise you're not constraining what you think you're constraining. It's not the kind of API approach that lets you fall into the pit of success, as it were. 
- Once we get the constraint right, we're severely limited in the functionality we can actually use in the body of the function template, because we only constrained on being a range and not on any actual members. `span`{:.language-cpp} gives us a common interface that we could use.
- There is no way to provide a read-only layer with concepts. If we use a hard constraint on allowing exactly ranges of `T const`{:.language-cpp}, we prevent users from passing non-const ranges - which would conceptually be safe. But if we allow non-const ranges, we implicitly allow them to be modified in the body of the function. No way to prevent that (or at least, if there is, it's going to be quite a bit more complicated than taking a `span<T const>`{:.language-cpp}).
- And even if we implement the body correctly, we're introducing a potentially massive amount of code bloat by way of lots of different instantiations for every container x value category x constness. All of these instantiations give us no benefit whatsoever, since `span` doesn't suffer from the typical type erasure performance hit.

There is zero benefit that I can think of to the constrained function template approach over writing a function that takes a `span` by value, and there are many significant disadvantages. 

And it actually gets worse than that, since even if the constrained function template approach had benefits - you would still need `span`. What if you want to _return_ a `span`? What if you wanted to pass a subset of a `vector` into the function, instead of the whole range? You need some lightweight representation to handle both of these situations, and that lightweight representation is `span`. Concepts don't help you with other of those problems at all.

### `span<T>`{:.language-cpp} vs `subrange<T*>`{:.language-cpp}

As mentioned at the top of this post, there are actually two different contiguous views in the standard library at the moment: `span<T>`{:.language-cpp} and, new with the addition of Ranges, `subrange<T*>`{:.language-cpp} (see [\[range.subrange\]](http://eel.is/c++draft/ranges#range.subrange)). While `span` is always a contiguous view, `subrange` is a more general abstraction that can be a view over any kind of iterators. It may be worth asking if we need _two_ contiguous views in the standard library, so let's go over the differences between these two types. There are a few main ones:

- The meaning of the template parameter. `span<T>`{:.language-cpp} is a contiguous view over a range whose `value_type` is `T`. `subrange<T*>`{:.language-cpp} is a contiguous view using two `T*`{:.language-cpp}s as iterators. The parameter just means something else. I give the advantage to `span` here, since it more directly represents what I want to say when I use such a type.
- The implicit conversions. `span<T>`{:.language-cpp} is constructible from any container which has `data()`{:.language-cpp} and `size()`{:.language-cpp}. This makes it extremely easy to use, since you can just pass arbitrary containers into it - this conversion is perfectly safe. On the other hand, `subrange<T*>`{:.language-cpp} is constructible from any container whose iterator type is `T*`{:.language-cpp}. This includes raw arrays, but may or may not include `vector<T>`{:.language-cpp}. This is a big advantage for `span`.
- Iterator specification. For `span<T>`{:.language-cpp}, the iterators are implementation defined (so as to allow implementations to diagnose bad access). For `subrange<T*>`{:.language-cpp}, they are `T*`. This is a win for `subrange`, although I think in practice, vendors will likely use `T*`{:.language-cpp} for `span` anyway.
- Quirks. There are some odd quirks for both types. `span<T>::cbegin()`{:.language-cpp} gives back an iterator that provides deep constness whereas `std::cbegin(span<T>)`{:.language-cpp} gives back an iterator that provides shallow constness. That's... odd. And as described earlier, it's questionable to provide deep constness for views. As Tim Song pointed out yesterday, `subrange<Base*>`{:.language-cpp} is currently constructible from `subrange<Derived*>`{:.language-cpp} - which is actively bad. This is less a quirk than a clear design defect that will probably go away before C++20 ships, so probably not even pointing out. Advantage `subrange` (hopefully).
- Fixed size. While the typical use of `span` will be to have a runtime-sized view, you can also have a fixed, compile-time-sized view by providing the second template parameter. `span<T, 2>`{:.language-cpp} is a contiguous view over 2 `T`s, and only requires a single `T*`{:.language-cpp} as its storage. There is no way to express this requirement in `subrange`{:.language-cpp}. 
- Generalizing to other iterators. In the same way, there is no way to express a non-contiguous view with `span`. So if you need a general sub-view, you would need to use `subrange`. 

Overall, for the problems that `span`{:.language-cpp} solves, `span` is a better solution than `subrange`. `span` is, indeed, the best `span`.
