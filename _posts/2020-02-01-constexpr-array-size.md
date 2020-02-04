---
layout: post
title: "The constexpr array size problem"
category: c++
tags:
  - c++
  - span
pubdraft: yes
---

This issue was first pointed out to me by Michael Park, and mostly explained to
me by T.C.

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

All compilers reject `s1` (gcc still accepted it when I started writing this post,
but [that bug](https://gcc.gnu.org/bugzilla/show_bug.cgi?id=66477) has been
fixed. That's some timing!)

### Wait, why?

All of these compilers are actually correct to reject this example. The reason is that in order
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

This case _has_ to be ill-formed, copying a function parameter during constant
evaluation means it has to itself be a constant expression, and function
parameters are not constant expressions - even in `constexpr`{:.language-cpp}
or `consteval`{:.language-cpp} functions. 

But if the `param` case is ill-formed, why does the `local` case work? An
unsatisfying answer is that... there just isn't any rule in [\[expr.const\]](http://eel.is/c++draft/expr.const#4)
that we're violating. There's no lvalue-to-rvalue conversion (we're not reading
through the reference in any way yet) and we're not referring to a reference (that's
the previous rule we ran afoul of). But the reason we violate the reference
rule is due to the underlying principle that the constant evaluator has to
reject all undefined behavior (UB is a compile error during constant evaluation!)
and so the compiler has to check that all references are valid. With the `param`
case, the compiler cannot know whether the reference is valid, so it must reject.
With the `local` case, the compiler can see for sure that a reference to `local`
would be a valid reference, so it's happy.

Notably, the rule we're violating is only about _references_. We can't write
a function that takes an array by value, so let's use the next-best thing:
`std::array`{:.language-cpp} and use the standard library's `std::size`{:.language-cpp}
([cppref](https://en.cppreference.com/w/cpp/iterator/size)):

```cpp
void check_arr_val(std::array<int, 3> const param) {
    std::array<int, 3> local = {1, 2, 3};
    constexpr auto s3 = std::size(local); // ok
    constexpr auto s4 = std::size(param); // ok
}
```

If `param` were a reference, the initialization of `s4` would be ill-formed (for
the same reason as previously), but because it's a value, this is totally fine.

So as long as you pass all your containers around by value, you're able to
use get and use the size as a constant expression. Which is the kind of thing
that's intellectually interesting, but also wildly impractical because obviously
nobody's about to start passing all their containers around _by value_.

### Why might we care?

Before getting into more detail about the problem itself, let's take a look at
why this matters. The following is just one motivating example. I picked it 
because it's probably the easiest to look at, but just keep in mind that this
is far from the only reason we might care about this sort of thing.

C++20 will have a new type `std::span`{:.language-cpp} ([cppref](https://en.cppreference.com/w/cpp/container/span), I've written about `span` before [here]({% post_url 2018-12-03-span-best-span %})),
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
are convertible to it. This conversion is safe, cheap, and desirable.

But that
isn't necessarily the case for `span<T, 5>`{:.language-cpp} - we certainly don't want that to
be implicitly constructible from `vector<T>`{:.language-cpp}, since how do we know if the incoming
vector has enough elements in it? The direction we're going
(see [P1976](https://wg21.link/p1976)) is that this
constructor will instead be `explicit`{:.language-cpp}. That is:

```cpp
void f(std::span<int, 5>);

std::vector<int> v3 = {1, 2, 3};
f(v3);                    // ill-formed
f(std::span<int, 5>(v3)); // compiles but UB

std::vector<int> v5 = {1, 2, 3, 4, 5};
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

How could we make this work?

We'd have to make the constraint something
like the following (other constraints omitted for brevity, like making sure
the range is actually contiguous and having the right underlying type):

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
change the way we query the size to query based on the type of the object
instead of the value of the object, we can side-step these problems:

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
        requires (type_size(type<std::remove_cvref_t<R>>)
                  == Extent);
    span(R&& r)
};
```

This works for both C arrays (the first overload) and `std::array`{:.language-cpp} (the second).
A similar approach was proposed in [P1419](https://wg21.link/p1419), the only
difference was that the proposal spelled this approach
`static_extent_v<std::remove_cvref_t<R>>`{:.language-cpp} instead
of `type_size(type<std::remove_cvref_t<R>>)`{:.language-cpp}.

But this can only work for a range whose size is encoded into its type. It can't
work for a range whose size is a constant expression - which is at least
conceptually what we want. One such range? Why `span`, of course:

```cpp
constexpr int arr[] = {1, 2, 3, 4, 5};
constexpr std::span<int> s = arr; 

// this is fine, s.size() is a constant expression
static_assert(s.size() == 5);

// ... but this still wouldn't work!
std::span<int, 5> fixed = s;
```

`s`'s size is a constant expression, but it's not tied to its type - these type-
based approaches wouldn't work. 

So it's, at best, a partial and unsatisfying solution. But at least it does
offer a way to reliably get the size of an array as a constant expression - it's
just that we have to go back to using a macro:

```cpp
#define ARRAY_SIZE(a) type_size( \
    type<std::remove_cvref_t<decltype(a)>>)
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
`x` is a sufficiently direct naming of the reference (for some as-yet defined
definition of sufficiently direct). This brings up other cases that would need
to be considered (courtesy of Richard Smith):


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

### The `emplace_back()`{:.language-cpp} problem

But _even then_, we're still stuck. We still have what I'm calling the vector
`push_back()`{:.language-cpp} / `emplace_back()`{:.language-cpp}
problem (I first pointed this out in D2089). How can we make all of these work:

```cpp
std::vector<std::span<int, 5>> bunch_of_spans;
bunch_of_spans.push_back(c_array);
bunch_of_spans.push_back(cpp_array);
bunch_of_spans.push_back(dynamic_span);

bunch_of_spans.emplace_back(c_array);
bunch_of_spans.emplace_back(cpp_array);
bunch_of_spans.emplace_back(dynamic_span);
```

The three calls to `push_back` all invoke a function whose signature would be:

```cpp
void push_back(std::span<int, 5> const&);
```

That is, the conversion to `span` happens on the way into the function. For
`dynamic_span`, it's still a constant expression here - so either we can still
treat it as a constant expression for constraint purposes (as with the function
parameter constraints approach in P1733) or we can add an overloaded constructor
to `span` that takes a constexpr range (as with constexpr parameter approach in
P1045). That part works fine.

But the three calls to `emplace_back()`{:.language-cpp} all invoke something that is roughly
equivalent to (this isn't exactly correct, but for the purposes of this discussion,
it's good enough):

```cpp
template <typename Arg>
void emplace_back(Arg&& arg) {
    push_back(std::span<int, 5>(std::forward<Arg>(Arg));
}
```

That is, the conversion so `span` happens _inside_ of `emplace_back()`{:.language-cpp}. In order
for this to still work for `dynamic_span`, we would need to somehow remember
that `arg` refers to a constant expression. And while `dynamic_span` is a constant
expression, `bunch_of_spans` doesn't have to be - this could be runtime code. 
How can this runtime call remember the "constant-expression-ness" of its
parameter? Ideally without having to touch `std::vector<T>::emplace_back`{:.language-cpp}
in any way whatsoever?

I have no idea. 

But I would love to get to the point where this code actually compiles:

```cpp
constexpr int c_array[] = {1, 2, 3, 4, 5};
constexpr std::span<int> dynamic_span = c_array;

std::vector<std::span<int, 5>> bunch_of_spans;
bunch_of_spans.emplace_back(dynamic_span);
```

### Recap

Basically, the best way to get the size of an array to be used as a constant
expression is still to use a macro - in C++, we can make that macro more type
safe than the initial C version, but still a macro.

Getting to the point where we can access the size of a range as a constant
expression - whether that size is part of the type (as it is for C arrays and
`std::array`{:.language-cpp}) or a variable part of a `constexpr`{:.language-cpp}
object (as it would be for a wide variety of ranges) - would require multiple language changes.

And none of the hypothetical language changes I've described in this post are
exactly trivial either, so I expect we'll have to live this problem for a while...