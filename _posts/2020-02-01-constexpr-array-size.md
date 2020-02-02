---
layout: post
title: "The constexpr array size problem"
category: c++
tags:
  - c++
  - span
pubdraft: yes
---

This issue was first pointed out to me by Michael Park.

Let's say I have an array, and I want to get its size and use it as a constant
expression. In C, we would write a macro for this:

```c
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(a[0]))
```

Macro notwithstanding, this works fine in all contexts. In C++, it unfortunately
also compiles for any types with overloaded `operator[]`{:.language-cpp} and
gives a nonsense result. Can we provide a type-safe way to do better?

We have `constexpr`{:.language-cpp}, so let's use it:

```cpp
template <typename T, size_t N>
constexpr size_t array_size(T (&)[N]) {
    return N;
}
```

This beats the C macro approach both by not being a macro and by not giving
bogus answers for `vector<T>`{:.language-cpp}. But it has possibly-surprising
limitations:

```cpp
void check(int const (&param)[3]) {
    int local[] = {1, 2, 3};
    constexpr auto s0 = array_size(local); // ok
    constexpr auto s1 = array_size(param); // error
}
```

gcc allows the declaration of `s1` here, while clang, msvc, and icc all reject it.

### Wait, why?

All of these compilers are actually correct to reject this example (and gcc is
incorrect in accepting it). The reason is actually quite simple: in order
for `array_size(param)`{:.language-cpp} to work, we have to pass that reference to `param` into
`array_size` - and that involves "reading" the reference. The specific rule
we're violating is [\[expr.const\]/4.12](http://eel.is/c++draft/expr.const#4.12).

This would be more obvious if our situation used pointers instead of references:

```cpp
template <typename T, size_t N>
constexpr size_t array_size(T (*)[N]) {
    return N;
}

void check(int const (*param)[3]) {
    constexpr auto s2 = array_size(param); // error, even on gcc
}
```

Given that gcc rejects this case but accepts the reference case, they probably
have some special casing for references. Not sure. 

This case _has_ to be ill-formed, copying a function parameter during constant
evaluation means it has to itself be a constant expression, and function
parameters are not constant expressions - even in `constexpr`{:.language-cpp}
or `consteval`{:.language-cpp} functions. 

But if the `param` case is ill-formed, why does the `local` case work? The
unsatisfying answer is that... there just isn't any rule in [\[expr.const\]](http://eel.is/c++draft/expr.const#4)
that we're violating. There's no lvalue-to-rvalue conversion (we're not reading
through the reference in any way yet) and we're not referring to a reference (that's
the previous rule we ran afoul of). 

Notably, the rule we're violating is only about _references_. We can't write
a function that takes an array by value, so let's use the next-best thing:
`std::array` and use the standard library's [`std::size`](https://en.cppreference.com/w/cpp/iterator/size):

```cpp
void check_arr_val(std::array<int, 3> const param) {
    std::array<int, 3> local = {1, 2, 3};
    constexpr auto s3 = std::size(local); // ok
    constexpr auto s4 = std::size(param); // ok
}
```

If `param` were a reference, the initialization of `s4` would be ill-formed (for
the same reason as previously), but beacuse it's a value, this is totally fine.

So as long as you pass all your containers around by value, you're able to
use get and use the size as a constant expression. Which is the kind of thing
that's intellectually interesting, but also wildly impractical because obviously
nobody's about to start passing all their containers around _by value_.

### Why might we care?

Before getting into more detail about the problem itself, let's take a look at
why this matters. The following is just one example, probably the easiest to
look at - but far from the only.

C++20 will have a new type [`std::span`{:.language-cpp}](https://en.cppreference.com/w/cpp/container/span)
(I've written about `span` before [here]({% post_url 2018-12-03-span-best-span %}),
which is a contiguous view on `T`. `span` comes in two flavors: dynamic extent
and fixed extent. Roughly speaking:

```cpp
// fixed-extent: always has size Extent, only needs
// to store a single pointer
template <typename T, size_t Extent = dynamic_extent>
struct span {
    T* ptr;
    
    constexpr T* begin() { return ptr; }
    constexpr T* end() { return ptr + Extent; }
    constexpr size_t size() const { return Extent; }
};

// dynamic-extent: size is variable, needs to store
// both pointer and size
template <typename T>
struct span<T, dynamic_extent> {
    T* ptr;
    size_t size;
    
    constexpr T* begin() const { return ptr; }
    constexpr T* end() const { return ptr + size; }
    constexpr size_t size() const { return size; }
};
```

It's not a complex type.

One of the big features of `span<T>`{:.language-cpp} is that all contiguous ranges over `T`
are convertible to it. This conversion is safe, cheap, and desirable. But that
isn't necessarily the case for `span<T, 5>`{:.language-cpp} - we certainly don't want that to
be implicitly constructible from `vector<T>`{:.language-cpp}, since how do we know if the incoming
vector has enough elements in it?

The direction we're going (see [P1976](https://wg21.link/p1976)) is that this
constructor will instead be `explicit`{:.language-cpp}. That is:

```cpp
void f(std::span<int, 5>);

std::vector<int> v3 = {1, 2, 3}, v5 = {1, 2, 3, 4, 5};
f(v3);                    // ill-formed
f(std::span<int, 5>(v3)); // well-formed but UB
f(std::span<int, 5>(v5)); // well-formed
```

But even with fixed-extent, there are some conversions that would be perfectly
safe to be implicit: arrays! Arrays have the size encoded in the type, we surely
know at compile time if an array has 5 elements or not, so this _could_ be
perfectly fine:

```cpp
void f(std::span<int, 5>);

int elems[] = {1, 2, 3, 4, 5};
f(elems); // perfectly safe, known statically
```

But this can't be made to work. We'd have to make the constraint something
like the following (other constraints omitted for brevity):

```cpp
template <typename T, size_t Extent>
struct span {
    template <range R>
    span(R&& r)
        requires (std::size(r) == Extent);
};
```

As already pointing out, since `r` is a reference, `std::size(r)`{:.language-cpp} cannot
be a constant expression, so this constraint cannot be made to work. This would
work fine if `r` was not a reference (but then we'd be constructing a `span` to
refer to a range that is about to get destroyed, so this is a particularly
tortured use of "work fine").

### Is there a library solution for this?

In the case I'm describing here, the size is encoded in the type. So if we
change the way we query the size to query based on the type instead of the value
of the object, we can side-step these problems:

```cpp
template <typename T> struct type_t { using type = T; };
template <typename T> inline constexpr type_t<T> type{};

template <typename T, size_t N>
constexpr size_t type_size(type_t<T[N]>) {
    return N;
};

template <typename T>
constexpr auto type_size(type_t<T>) -> decltype(T::size()) {
    return T::size();
}

template <typename T, size_t Extent>
struct span {
    template <range R>
        requires (type_size(type<std::remove_cvref_t<R>>) == Extent);
    span(R&& r)
};
```

This works for both C arrays (the first overload) and `std::array`{:.language-cpp} (the second).
A similar approach was proposed in [P1419](https://wg21.link/p1419),
just spelled `std::static_extent_v<std::remove_cvref_t<R>>`{:.language-cpp} instead
of `type_size(type<std::remove_cvref_t<R>>)`{:.language-cpp}.

But this can't work for any range whose size could still be a constant expression
but whose size is not encoded into the type. Such as, for instance:

```cpp
constexpr int arr[] = {1, 2, 3, 4, 5};
constexpr std::span<int> s = arr; 

// this is fine, s.size() is a constant expression
static_assert(s.size() == 5);

// ... but this still wouldn't work
std::span<int, 5> fixed = s;
```

So it's, at best, a partial and unsatisfying solution. But at least it does
offer a way to reliably get the size of an array as a constant expression - it's
just that we have to go back to using a macro:

```cpp
#define ARRAY_SIZE(a) type_size(type<std::remove_cvref_t<decltype(a)>>)
```

All this `constexpr`{:.language-cpp} machinery, and the best we can do is really only a little
bit better than C.

### Is there a language solution for this?

There is no library solution for this, maybe there's a language one? The obvious
language rule would be to say something like: simply passing around a reference
from one function to another is fine - it's not until you actually _need_ the
reference for something that we start requiring it to be a valid constant
expression. That is, we have to read through the reference in some way or do
some operation that requires the address to be known, something in that vein.

A different, less generous, way to describe a feature like this would be to say
that `x.f()`{:.language-cpp} can still be a constant expression even if `x` is
a reference to unknown object, as long as `f` is a static member function and
`x` is a sufficiently direct naming of the reference. And there are other cases
to consider (courtesy of Richard Smith):

- `(*ptr_to_array)->size()`{:.language-cpp}?
- `(*ptrs_to_arrays[3])->size()`{:.language-cpp}? What about if `ptrs_to_arrays`
was actually an array of only 2 arrays, at which point we'd surely want to reject
this during constant evaluation in the same way we reject out-of-bounds access
generally?

And if we do still do bounds checking in the latter case, is there actually a
line we can draw for which things we do on the left-hand-side (like this
bounds-check) but which things we don't (like actually require that
`*ptrs_to_arrays[3]`{:.language-cpp} is a constant expression itself)?

Moreover, even if we go this direction. Let's say that we come up with some
kind of exception in this space, such that the original code we tried to 
write actually works. Just reproducing the relevant code for proximity:

```cpp
template <typename T, size_t Extent>
struct span {
    template <range R>
    span(R&& r)
        requires (std::size(r) == Extent);
};

void f(span<int, 5>);

int c_array[5];
std::array<int, 5> cpp_array;

f(c_array);   // now ok
f(cpp_array); // now ok
```

Would this even be a sufficient rule? Still no! It still wouldn't work for the
example I showed earlier:

```cpp
constexpr std::array<int, 5> some_const_array = {1, 2, 3, 4, 5};
constexpr std::span<int> dynamic_span = some_const_array; // ok
static_assert(dynamic_span.size() == 5); // ok

f(dynamic_span); // still error!
```

Even if we say that we can propagate references to our heart's delight during
constant evaluation, as long as we don't read them, that wouldn't help us here.
`dynamic_span` is a dynamic `span`, its `size()`{:.language-cpp} member function
is non-static, so we very much do need to read through the reference. 

In order to make this example work, we'd need to not only have a reference
propagation rule (to make the `c_array` and `cpp_array` cases work), but we'd
also need to adopt something like function parameter constraints (see [P1733](https://wg21.link/p1733)
and [P2049](https://wg21.link/p2049), and my response [D2089](https://brevzin.github.io/cpp_proposals/2089_param_constraints/d2089r0.html))
or, better, `constexpr`{:.language-cpp} function parameters (see [P1045](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2019/p1045r1.html)).
Either way, these proposals would _only_ help the `dynamic_span` case - with
the array cases, since the arrays themselves aren't constant expressions,
none of what they are suggesting would help. We'd need both.

### Recap

Basically, the best way to get the size of an array to be used as a constant
expression is still to use a macro - in C++, we can make that macro more type
safe than the initial C version, but still a macro.

Getting to the point where we can access the size of a range as a constant
expression - whether that size is part of the type (as it is for C arrays and
`std::array`{:.language-cpp} or a variable part of a `constexpr`{:.language-cpp}
object - would require multiple language changes.

And none of the hypothetical language changes I've described in this post are
exactly trivial either, so I expect we'll have to live this problem for a while...