---
layout: post
title: "Named Template Arguments"
category: c++
tags:
  - c++
  - c++20
---

C++, unlike many other programming languages, doesn't have named function parameters or named function arguments. I hope it will someday, it's a language feature that I find has large benefits for readability. Until then, in C++20, we actually have the ability to do a decent approximation not only of named function arguments but also named template arguments.

## Named Function Arguments

The best way to approxiate named parameters in C++ is to use one of the new C++20 language features: [designated initializers](https://en.cppreference.com/w/cpp/language/aggregate_initialization#Designated_initializers) (although gcc and clang have supported it for many years as an extension). Instead of writing something like:

```cpp
void takes_point(int x=0, int y=0);

takes_point(1, 2);
```

we can write:

```cpp
struct Point {
   int x = 0;
   int y = 0;
};

void takes_point(Point);

takes_point({.x=1, .y=2}); // x=1, y=2
takes_point({.y=3});       // x=0, y=3
takes_point({.x=4});       // x=4, y=0
takes_point({.y=5, .x=6}); // ill-formed
```

The last one is ill-formed because in C++ (unlike C), designated initializers must be listed in declaration order. So unlike other languages with named parameters, we do have this limitation - we have to provide the arguments in order - and do we have to do extra work by declaring an extra struct (as opposed to just taking two `int`{:.language-cpp} arguments named `x` and `y`).

But at least this lets us name arguments, and lets us use default arguments without having to name them (note that the second call above just provides a value for `y`, we didn't have to come up with a way to say "use the default for `x`")... at the cost of having to write a struct per function.

But that's function arguments, what about template arguments?

## Class types as non-type template parameters

One of the big new language features in C++20, and one that has changed quite a bit over the last couple years, is the ability to use class types as non-type template parameters (also known as value template parameters). For those of you that have followed the standardization process a bit, but not super closely, you may be a bit confused as to what the rules actually are, so here's a quick, non-exhaustive rundown.

In C++17, non-type template parameters had to be one of: integral/enum types, pointers to object/function, lvalue references to object/function, pointers to member, or `std::nullptr_t`{:.language-cpp}. With a few extra requirements (e.g. a pointer to object has to point to an object, not a subobject, that must have static storage duration).

In C++20, this list is expanded greatly. Initially, [P0732](https://wg21.link/p0732)'s rule set added class types with defaulted `operator<=>`{:.language-cpp} (recursively all the way down) whose return type must be either `std::strong_ordering`{:.language-cpp} or `std::strong_equality`{:.language-cpp}. This was modified slightly by [P1185](https://wg21.link/p1185) to be based on defaulted `operator==`{:.language-cpp} (recrusively all the way down).

But this equality-based model has some serious issues, and would additionally limit our ability to extend this functionality to include non-type template parameters of type `std::string`{:.language-cpp} or `std::optional<T>`{:.language-cpp} (neither of which could have defaulted comparisons). In Belfast, we adopted [P1907](https://wg21.link/p1907) which introduces the idea of a _structural type_. In C++20, a class type is structural if all of its bases and non-static data members are public, non-mutable, and structural. In C++23, the intent is to come up with a way to provide a custom way to mangle a type (the floated idea has been something like `operator template()`{:.language-cpp}).

There is a lot that can, and should, be written about this topic. This is just a quick fly-by introduction. But importantly, the `Point` type I showed earlier _can_ be used as a non-type template parameter in C++20: all of its members are public, non-mutable, and structural (all scalar types are structural).

## Named Non-type Template Arguments

Similar the above example, where today we might write:

```cpp
template <int x=0, int y=0>
void takes_tmpl_point();

takes_tmpl_point<1, 2>();
```

We can combine the ability to have class types as non-type template parameters with the ability to use designated initializers to write basically the same code we had earlier to name our function arguments:

```cpp
struct Point {
   int x = 0;
   int y = 0;
};

template <Point> // ok in C++20
void takes_tmpl_point();

takes_tmpl_point<{.x=1, .y=2}>(); // x=1, y=2
takes_tmpl_point<{.y=3}>();       // x=0, y=3
takes_tmpl_point<{.x=4}>();       // x=4, y=0
takes_tmpl_point<{.y=5, .x=6}>(); // ill-formed
```

I think this is pretty nice, for the same reasons I think the earlier example of named function arguments with designated initializers is nice.

But this is a way to provide named _values_, do we have a way of providing named _types_ too?

## Named Type Template Arguments

The declaration of `std::unordered_map`{:.language-cpp} is:

```cpp
template<
    class Key,
    class T,
    class Hash = std::hash<Key>,
    class KeyEqual = std::equal_to<Key>,
    class Allocator = std::allocator<std::pair<const Key, T>>
> class unordered_map;
```

Five template parameters, three of which are defaulted. If you only want to change the `Hash` parameter, you can provide just the first three. But if you _only_ want to change the allocator, you still have to provide all five. If you _only_ want to change the equality comparison, you have to remember that the hash goes first. It's annoying, in the same way calling a function with lots of arguments is annoying -- when you cannot name the arguments, it's difficult to read. 

With C++20, we can combine the mechanism we used earlier (using class types as non-type template parameters with designated initializers), with another new C++20 language feature: class template argument deduction for aggregates ([P1021](https://wg21.link/p1021) with wording in [P1816](https://wg21.link/p1816)). What we can do is create an aggregate built up of members that are basically types-as-values:

```cpp
template <typename T>
struct type_t {
    using type = T;
};

template <typename T>
inline constexpr type_t<T> type{};

template<
    class Key,
    class T,
    class Hash = std::hash<Key>,
    class KeyEqual = std::equal_to<Key>,
    class Allocator = std::allocator<std::pair<const Key, T>>
>
struct unordered_map_types
{
    type_t<Key> key;
    type_t<T> value;
    type_t<Hash> hash = {};
    type_t<KeyEqual> key_equal = {};
    type_t<Allocator> allocator = {};
};

template <unordered_map_types Types>
class unordered_map {
    // no 'typename' necessary here in C++20
    using Key = decltype(Types::key)::type;
    using T = decltype(Types::value)::type;
    // etc.
};
```

The `Types` template parameter for this new declaration of `unordered_map` is a non-type template parameter using the placeholder type `unordered_map_types` - this is using class template argument deduction for the template parameter. The class template `unordered_map_types` is structural, all of its members are public and all of those types have no members. This all is valid C++20.

As far as the usage?

```cpp
// equivalent to std::unordered_map<int, int>
using A = unordered_map<{.key=type<int>, .value=type<int>}>;
```

`type<int>`{:.language-cpp} is a variable template of type `type_t<int>`{:.language-cpp}. Using the new ability to do class template argument deduction from designated initializers, we can deduce the type `unordered_map_types<int, int, std::hash<int>, std::equal_to<int>, std::allocator<std::pair<int const, int>>>`{:.language-cpp}. 

This is already neat. But where it gets even neater is the ability to not have to provide all the defaults:

```cpp
// specifying a custom allocator without having
// to also specify the default hash/equality types
using B = unordered_map<{.key=type<string>,
    .value=type<int>,
    .allocator=MyAllocator}>;
```

Or even when you do want to use all the types, naming them just makes it more obvious what's going on, even at the cost of all of these extra `type<>`{:.language-cpp}s:

```cpp
using C = unordered_map<{.key=type<string>,
    .value=type<string>,
    .hash=type<CustomHash>,
    .equal=type<CaseInsensitiveCompare>,
    .allocator=type<PoolAllocator>}>;
```

You can use this trick to mix and match between type and non-type parameters as well:

```cpp
template <typename T>
struct small_vector_args {
    type_t<T> type;
    size_t N;
};

template <small_vector_args Args>
struct small_vector {
    using value_type = decltype(Args::type)::type;
    static constexpr auto small_size = Args.N;
    
    // implementation here
};

// instead of small_vector<int, 4>
using D = small_vector<{.type=type<int>, .N=4}>;
```

## Just... Neat

While C++20 still won't have named function parameters or named template parameters, this combination of designated initializers and class types as non-type template parameters at least allows us to do an okay job of approximating named function and template arguments -- at the cost of some boilerplate on the callee side and extra punctuation on the caller side. 

It's not a perfect substitute for a real language feature, and I hope we get such a thing at some point. Until then, I'm not saying you should or should not use this approach. I'm just saying I think it's pretty neat.