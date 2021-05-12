---
layout: post
title: "Ambiguity in template parameters"
category: c++
tags:
  - c++
  - c++20
  - templates
---

C++ has had three kinds of template parameters since basically always: type template parameters (the vast majority), non-type template parameters (sometimes called value template parameters, which strikes me as a better term), and template template parameters (parameters that are themselves templates, the rarest of the three).

From C++98 up through and including C++17, these three kinds were very easily distinguishable by syntax:

* template type parameters are always introduced by `class` or `typename`
* template template parameters are always introduced by `template </* some parameters */> class` or, since C++17, `template </* some parameters */> typename`
* anything else is a non-type template parameter (I'm excluding the case where you might have something like `#define Iterator class`)

The kinds of values you could use as value template parameters has greatly been increased from C++98 to C++17 (it used to be quite limited), but the syntactic form of template parameters really hadn't changed all that much. The introduction of `auto` non-type template parameters in C++17 was a new form of parameter, but the `auto` keyword still makes it quite obvious that this is a value parameter and not a type or a template parameter.

As a result, if looking through unfamiliar code, you came across `template <Kind Name>` where you didn't know what `Kind` was, you could rightly conclude that this is a non-type template parameter. Indeed, in C++17, I would guess that it's most likely some kind of enumeration, following by an alias for an integer type, followed by an alias for a function pointer type. But, importantly, you know for sure that it's a value - because types are always introduced by `class` or `typename` and templates are introduced by `template`. You might not know yet what actual type `Kind` is, but at least you do know that it _is_ a type.

This all changes dramatically in C++20 due to a confluence of several features.

## Concepts

One of the major new language features in C++20 is concepts, which allow us to write constrained templates as a proper language feature. And one of the early realizations in concepts design was the combination of factors that:

1. type parameters are extremely common,
2. type parameters often need to be constrained somehow, and
3. the introduces `class` and `typename` really are kind of noise anyway

And so as early as 2003 ([N1536](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2003/n1536.pdf)), even before we have any other aspect of concepts that is recognizable as C++20 concepts, we have the introduction of concepts _in place of_ the `class` and `typename` introducers:

```cpp
template <Iterator I>
void f(I it);
```

Note that in this paper, we don't even have the notion of a `requires` clause yet (or a `where` clause, as some earlier papers spelled it). Although today we would recognize this syntax as being a convenient short-hand for:

```cpp
template <typename I>
    requires Iterator<I>
void f(I it);
```

## Class Types as Non-Type Template Parameters

Another new language feature in C++20 ([P0732](https://wg21.link/p0732) and then [P1907R0](https://wg21.link/p1907r0) and [P1907R1](https://wg21.link/p1907r1) - I'm deliberately linking both) was extending the allowable set of types that could be used as non-type template parameters to include some class types. In the original design, the restriction was based on a defaulted `<=>` while in the new design the restriction is based on having all base classes and members public. 

As a simple example, this means that the following is valid in C++20 whereas it was ill-formed before then:

```cpp
struct Point { int x; int y; };

template <Point P> struct Widget { };
```

Now, when we combine this feature (allowing class types) with a feature we already had (class template argument deduction, from C++17), we end up being able to write something as follows:

```cpp
template <size_t N>
struct fixed_string {
    char data[N];
    
    constexpr fixed_string(char const (&d)[N]) {
        std::ranges::copy(d, data);
    }
};

template <fixed_string S> struct A { };

// a's template parameter is a fixed-string<6>
A<"hello"> a;
```

This is a very important piece of functionality since we cannot have a string literal as a template argument (a somewhat inherent problem since you want `A<"hello">` to be the same type across all translation units but it's hard to make the string literals "equal" in the sense that they need to be) and we cannot _yet_ have `std::string` as the type of a non-type template parameter parameter (still have to figure out how to teach the compiler to mangle/demangle this case), so this `fixed_string` approach is currently our only way to have strings as template arguments. 

## Putting it all together

What does this mean for being able to read unknown code? 

In C++17 (as in C++98), when you see `template <Kind Name>`, you knew for sure that this was a non-type template parameter and that `Kind` was a type (and that type is probably an enumeration). 

But in C++20, when you see `template <Kind Name>`, you really don't know what this could be. We could have:

1. `Name` is a type which models the concept `Kind`.
2. `Name` is a value whose type is `Kind`, but now `Kind` can also be a class type in addition to a scalar type
3. `Name` is a value whose type is some specialization of the class template `Kind`.

It's still really early to be able to stay with confidence which of these cases will end up being the most common, but simply because template type parameters are by far the most common, I would guess that constrained type will eventually overtake non-type template parameter as far as this syntax is concerned (that is, I'd expect the order I listed above to be the order of likelihood).

This lack of distinction in kinds was something that I became very aware of when I was exploring Mateusz Pusz's [units library](https://github.com/mpusz/units) (which is quite good!). That library makes use of various new C++20 facilities, including constrained templates and class types as non-type template parameters. But it does mean that you might not know what these things are:

```cpp
template <basic_fixed_string Symbol, Unit U>
    requires U::is_named
struct base_dimension { ... };

template <BaseDimension D1, BaseDimension D2>
struct base_dimension_less { ... };
```

Here, I know that `Symbol` is a non-type template parameter whose type is a specialization of `basic_fixed_string` (because I'm familiar with this structure, and indeed just showed it in the previous section). And I can deduce that `U` has to be a type constrained by the concept `Unit` due to the additional requirement that `U::is_named` (since `U` cannot be a value with that syntax, it must be a type).

But are `D1` and `D2` types or values? `BaseDimension` seems unlikely to be a class template in this context (but it... could be) and if you don't know how dimensions are defined in this library yet, you could conceive of a `BaseDimension` being a specific type that you have instances of. Although if `D1` and `D2` were values, why would we need a type to compare them, wouldn't we just use `<`?

The most fun example in the whole library is:

```cpp
template <typename Child,
          basic_symbol_text Symbol,
          PrefixFamily PF,
          ratio R,
          Unit U>
  requires UnitRatio<R>
struct named_scaled_unit { ... };
```

Now, in this particular library, we can take advantage of naming convention to help us out dramatically. If I told you that concepts were always `PascalCase` while class types were always `snake_case`, it would really help us differentiate what's going on here:

* `Child` is a type (this is the freebie, because of `typename`)
* `Symbol` is a value, whose type is a specialization of `basic_symbol_text` (the `basic_*` here is the hint, this is the same shape as the `basic_fixed_string` we saw earlier)
* `PF` is a type, constrained on the concept `PrefixFamily`
* `R` is a value, whose type is `ratio`
* `U` is a type, constrained on the concept `Unit`

This is fun because we have four different kinds of template parameters here (unconstrained type, constrained type, value of class type, and value of class template specialization) and only one of these could even have been written in C++17!

But we really needed the naming convention to help us understand what's going on here. Unfortunately, the concepts in the C++20 standard library are all `snake_case` and since lots of other libraries follow the standard library naming conventions, we wouldn't have this help.

## Could we have done things differently?

That's really the obvious question. Was there a different syntax choice we could have made that would have made unfamiliar code easier to understand? Now, it's not like simply knowing that `PF` is a type and `R` is a value in the above class template declaration automatically means you understand the code. What's a `ratio`? What's a `PrefixFamily`? You still probably don't know (although you can probably at least guess what a `ratio` is). But it does help a lot in simply knowing that one is a type and one is a value.

The simplest change would have been to not have the _type-constraint_ syntax. So the above declaration would have to have been:

```cpp
template <typename Child,
          basic_symbol_text Symbol,
          typename PF,
          ratio R,
          typename U>
  requires UnitRatio<R>
       and PrefixFamily<PF>
       and Unit<U>
struct named_scaled_unit { ... };
```

And now obviously `PF` and `U` are types. But this isn't really satisfactory, since most template parameters are types and a lot of them really should be constrained, so having a lot of syntax to do so... kind of sucks?

The way I really wish we could go would be a much more dramatic change, to spell it something like this:

```cpp
template <Child,
          basic_symbol_text Symbol,
          PF: PrefixFamily,
          ratio R,
          U: Unit>
  requires UnitRatio<R>
struct named_scaled_unit { ... };
```

This is shorter than what's in the actual library and would be completely unambiguous to humans. What I'm doing here is changing template type parameters to have _no_ introducer at all (no `typename` or `class`) but can instead take an optional trailing constraint after a `:`. 

This syntax is ambiguous with syntax we have today, since I have been able to write this since always:

```cpp
typedef int Identifier;

template <Identifier> struct X { };
```

Where this declares a class template that takes a non-type template parameter of type `int` with no name. But anonymous parameters really encroach on the syntax space - they're rare (usually when you have parameters it's because you want to use them for something) and the cost of adding a name for a parameter is exceedingly small (you could use `_`, or silly variations like `_1`, `_2`, ...).

I think it'd be much more valuable to change the syntax above to instead mean a class template that takes a single _type_ parameter _named_ `Identifier`. This follows the motivation of all the original concept papers: the `typename` or `class` introducers are kind of just line noise that doesn't mean anything. They reused that slot to be able to add a constraint, which is a much more meaningful use of a syntax. But unfortunately that means that now reading template declarations is ambiguous (to humans, not to compilers). 

Of course, C++ cannot change in this direction because it would dramatically change the meaning of some existing code.

Unless we added epochs... 