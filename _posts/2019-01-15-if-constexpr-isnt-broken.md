---
layout: post
title: "if constexpr isn't broken"
category: c++
tags:
 - c++
 - c++20
 - d
--- 

Andrei Alexandrescu's Meeting C++ Keynote [The Next Big Thing](https://www.youtube.com/watch?v=tcyb1lpEHm0) was just posted recently on YouTube. I am a big fan of Andrei on a number of levels - he is very much my idol. This last talk that he gave was about the limitations of `if constexpr`{:.language-cpp} as compared to "another language" and how C++ should do better (to put it mildly). Having watched it, I have to say that on the whole I'm not impressed with the arguments and I disagree with his conclusion. I think the language tools we will have in C++20 actually achieve most of what he is trying to achieve. I'm just not convinced that `if constexpr`{:.language-cpp} needs a fix - certainly not one as dramatic as he is selling in the talk. Consider this post my counterargument.

Or, as Andrei would say, my attempt to DESTROY!

There _are_ a few things that we can't do _super_ well in C++, and arguably we should try to do better. I will certainly mention those as they come up. Also, just a brief disclaimer up front: I have written 0 lines of "another language" in my life so it is extremely likely that my understanding of some of the details of the implementation of his `Checked` type are totally wrong. Please correct me if this is the case. But I'm hoping that I'm at least close enough to right to make a reasonable argument.

<hr />

With that out of the way, D's `static if`{:.language-d} language feature is roughly used for three broad categories of things: 

1. Conditionally enabling classes or functions
2. Conditionally controlling the implementation of a function
3. Conditionally adding members to a class

All based on template parameters. It's just the one language feature that does all of these things together, which probably makes it easy to just pick up and use (I can only speak hypothetically). 

One very significant thing that `static if`{:.language-cpp} does in D, that Andrei makes very clear that he thinks is a salient feature and a significant shortcoming of `if constexpr`{:.language-cpp}, is that it does _not_ introduce scope. One of the slides he shows in his talk (#28) looks like this:

```cpp
template <class K, class V, size_t maxLength>
struct RobinHashTable {
  static if (maxLength < 0xFFFE) {
    using CellIdx = uint16_t;
  } else {
    using CellIdx = uint32_t;
  }
};
```

With the idea here being that `RobinHashTable<K,V,4>::CellIdx`{:.language-cpp} would exist and be `uint16_t`{:.language-cpp} while `RobinHashTable<K,V,0x10000>::CellIdx`{:.language-cpp} would exist and be `uint32_t`{:.language-cpp}. The `if`{:.language-cpp} there doesn't introduce scope. The class can go on and have variables of type `CellIdx` and so forth.

But... do we need a new language feature for that? We can do that already, it looks like:

```cpp
template <class K, class V, size_t maxLength>
struct RobinHashTable {
  using CellIdx = std::conditional_t<
    (maxLength < 0xFFFE), uint16_t, uint32_t>;
};
```

or to avoid traits:

```cpp
static constexpr auto get_type() {
    if constexpr (maxLength < 0xFFFE) {
        return type<uint16_t>;
    } else {
        return type<uint32_t>;
    }
}

using CellIdx = decltype(get_type())::type;
```

And this kind of nagging "But... we can already do this?" thought followed me throughout the rest of his talk. So I thought I'd go through his checked numerics type, `Checked<T, Hook>`{:.language-cpp} in C++ terms, and see how well we could implement it (the D code can be found [here](https://github.com/dlang/phobos/blob/23f600ac78591391f7009beb1367fb97bf65496c/std/experimental/checkedint.d)). Do we have to go through a lot of gymnastics? How painful is it really? 

### Enabling classes or functions

The first thing `static if`{:.language-cpp} can do in D is to conditionally enable a class template or a function template based on its template parameters. And we see that right off the bat when we declare it:

```d
struct Checked(T, Hook = Abort)
if (isIntegral!T || is(T == Checked!(U, H), U, H))
{
  // ...
}
```

This declares a class template `Checked`, with two template parameters: `T` and `Hook`, that is constrained such that the type `T` is either `Integral` or a specialization of `Checked` (the syntax `isIntegral!T`{:.language-d} is equivalent to `isIntegral<T>`{:.language-cpp} in C++ - D just uses a single `!`{:.language-d} for parsing reasons). 

In C++20, we have a language feature for that: Concepts. Besides the built-in `is`{:.language-d} expression, we can do the rest in C++ fairly equivalently:

```cpp
template <typename T, typename Hook = Abort>
struct Checked;

template <typename T, typename Hook>
  requires Integral<T> || Specializes<T, Checked>
struct Checked
{
    // ...
};
```

Okay, we have to forward declare the type so that the name is in scope to be used in the _requires-expression_ and we have to define this `Specializes` concept somewhere. So I guess slight edge to D there. What about the member functions?

```d
auto opBinary(string op, Rhs)(const Rhs rhs)
if (isIntegral!Rhs || isFloatingPoint!Rhs || is(Rhs == bool))
{
    // ...
}
```

can be written as (note that in C++, `bool`{:.language-cpp} satisfies `Integral`):

```cpp
template <typename F, typename Rhs>
    requires Integral<Rhs> || FloatingPoint<Rhs>
auto opBinary(F op, Rhs rhs) {
    // ..
}
```

and so forth. Actually we'd probably do a bit better here and say:

```cpp
template <typename F, Numeric Rhs>
    requires Invocable<F, T, Rhs>
auto opBinary(F op, Rhs rhs) {
    // ...
}
```

All the member functions are just variations on this theme, some with way more cases than others:

```d
this(U)(U rhs)
if (valueConvertible!(U, T) ||
    !isIntegral!T && is(typeof(T(rhs))) ||
    is(U == Checked!(V, W), V, W) &&
        is(typeof(Checked!(T, Hook)(rhs.get))))
{ /* ... */ }
```

which I would just write as two constructors:

```cpp
template <typename U>
    requires ValueConvertible<U, T> ||
        !Integral<T> && Constructible<T, U>
Checked(U ) { /* ... */ }

template <typename U, typename H>
    requires ValueConvertible<U, T> ||
        !Integral<T> && Constructible<T, U>
Checked(Checked<U,H> ) { /* ... */ }
```

Basically all of these cases can be directly translated to C++ without much fuss. It's basically just a difference in syntax. The D versions are certainly terser, but I don't feel like they're significantly better or that we're missing out on something important.

### Controlling implementation

D's `static if`{:.language-d} can also control at compile time what actually happens within a function body. Here is the conversion function template to an arbitrary numeric type:

```d
U opCast(U, this _)()
if (isIntegral!U || isFloatingPoint!U || is(U == bool))
{
    static if (hasMember!(Hook, "hookOpCast"))
    {
        return hook.hookOpCast!U(payload);
    }
    else static if (is(U == bool))
    {
        return payload != 0;
    }
    else static if (valueConvertible!(T, U))
    {
        return payload;
    }
    // may lose bits or precision
    else static if (!hasMember!(Hook, "onBadCast"))
    {
        return cast(U) payload;
    }
    else
    {
        if (isUnsigned!T || !isUnsigned!U ||
                T.sizeof > U.sizeof || payload >= 0)
        {
          auto result = cast(U) payload;
          // If signedness is different, we need additional checks
          if (result == payload &&
                (!isUnsigned!T || isUnsigned!U || result >= 0))
            return result;
        }
        return hook.onBadCast!U(payload);
    }
}
```

Look at all this combinatorial, design-by-introspection stuff going on here. Surely, C++ can't compare with this at all. 

But we have a tool for this one too. Andrei might think it's broken, but it actually was basically design to solve exactly this case and it works great for it: `if constexpr`{:.language-cpp}. Combine it with Concepts, and I can write basically exactly the same code:

```cpp
template <Numeric U>
operator U()
{
    if constexpr (requires { hook.template opCast<U>(payload) })
    {
        return hook.template opCast<U>(payload);
    }
    else if constexpr (Same<U, bool>) {
    {
        return payload != 0;
    }
    else if constexpr (ValueConvertible<T, U>)
    {
        return payload;
    }
    // may lose bits or precision
    else if constexpr (!requires {
        hook.template onBadCast<U>(payload) })
    {
        return static_cast<U>(payload);
    }
    else
    {
        if (!UnsignedIntegral<T> || !UnsignedIntegral<U> ||
                sizeof(T) > sizeof(U) || payload >= 0)
        {
          auto result = static_cast<U>(payload);
          // If signedness is different, we need additional checks
          if (result == payload &&
                (!UnsignedIntegral<T> || UnsignedIntegral<U> ||
                    result >= 0))
            return result;
        }
        
        return hook.template onBadCast<U>(payload);
    }
}
```

Alright, what's the difference? We have this nuisance with the `template`{:.language-cpp} keyword due to `hook` being dependent. Unlike D, we have to write out the full expression we're checking the `Hook` for, not simply if it has a particular member by name (maybe reflection will give us that). Otherwise, this is... nearly identical yeah? 

That's basically the sum total difference right there - a somewhat more awkward and uglier, yet slightly more correct way of checking presence of particular hooks. But all the functionality is right there. We're not _missing_ anything.

### Adding members to a class

The last way that `static if`{:.language-d} is used in D is to conditionally add members to a class and control how they're used. This feature has a few different flavors on display in this one class. 

We have conditional initialization:

```d
static if (hasMember!(Hook, "defaultValue"))
    private T payload = Hook.defaultValue!T;
else
    private T payload;
```

Because we have either initialization or no initialization, our only real option is to go the route of a defaulted constructor for the fallback case:

```cpp
Checked() = default;

Checked() requires requires { Hook::template defaultValue<T>() }
   : payload(Hook::template defaultValue<T>())
{ }
```

Here we have a new kind of awkwardness with the necessary duplication of `requires requires`{:.language-cpp} (which I've always assumed was necessary due to parsing ambiguity... but I'm not entirely sure), and the same awkwardness with the `template`{:.language-cpp} keyword, but it works. The other form in which this kind of initialization appears is a little easier for us to deal with:

```d
static if (hasMember!(Hook, "max"))
    enum Checked!(T, Hook) max = Checked(Hook.max!T);
else
    enum Checked!(T, Hook) max = Checked(T.max);
```

Because now both cases are initialized, we can just use a lambda (or alternatively have function overloads):

```cpp
static constexpr Checked max = []{
    if constexpr (requires { Hook::template max<T>() }) {
        return Hook::template max<T>();
    } else {
        return std::numeric_limits<T>::max();
    }
}();
```

There's another case where we have a member when the type is non-empty, otherwise we just alias the type:

```d
static if (stateSize!Hook > 0) Hook hook;
else alias hook = Hook;
```

Which actually we can do even easier in C++ with our new attribute:

```cpp
[[no_unique_address]] Hook hook;
```

One thing that D would let you do that isn't used in `Checked` but would be a clear win over C++ would be having a conditional member with no fallback. An example of this can be found in the specification of [`std::ranges::split_view`{:.language-cpp}](http://eel.is/c++draft/range.split.view):

```cpp
// exposition only, present only if !ForwardRange<V>
iterator_t<V> current_ = iterator_t<V>();
```

which in D could just be:

```d
static if (!ForwardRange!V) iterator_t!V current_ = iterator_t!V();
```

But the best way we can do that in C++ today is this mess:

```cpp
struct empty { };
using current_t = std::conditional_t<
    !ForwardRange<V>, iterator_t<V>, empty>;
[[no_unique_address]] current_t current_ = current_t();
```

Which is technically equivalent, but clearly horrific.

### `opBinary()`{:.language-d} overloading

Separate from the question of `if constexpr`{:.language-cpp}, but related to a different issue Andrei touched on in the talk related to terseness of implementation, is how the D language treats operator overloading. In C++, you overload `operator+`{:.language-cpp} and `operator-`{:.language-cpp} and `operator*`{:.language-cpp} and ... In D, instead, you overload a function named `opBinary()`{:.language-d} that takes as a template parameter a compile-time `string`{:.language-d} that has as its value the operator being overloaded. 

So the way that `Checked` implements _all_ the binary operators whose right-hand side is a numeric type is:

```d
auto opBinary(string op, Rhs)(const Rhs rhs)
if (isIntegral!Rhs || isFloatingPoint!Rhs || is(Rhs == bool))
{
    return opBinaryImpl!(op, Rhs, typeof(this))(rhs);
}

auto opBinary(string op, Rhs)(const Rhs rhs) const
if (isIntegral!Rhs || isFloatingPoint!Rhs || is(Rhs == bool))
{
    return opBinaryImpl!(op, Rhs, typeof(this))(rhs);
}

private auto opBinaryImpl(string op, Rhs, this _)(const Rhs rhs)
{
    alias R = typeof(mixin("payload" ~ op ~ "rhs"));
    static assert(is(typeof(mixin("payload" ~ op ~ "rhs")) == R));
    static if (isIntegral!R) alias Result = Checked!(R, Hook);
    else alias Result = R;

    static if (hasMember!(Hook, "hookOpBinary"))
    {
        auto r = hook.hookOpBinary!op(payload, rhs);
        return Checked!(typeof(r), Hook)(r);
    }
    else static if (is(Rhs == bool))
    {
        return mixin("this" ~ op ~ "ubyte(rhs)");
    }
    else static if (isFloatingPoint!Rhs)
    {
        return mixin("payload" ~ op ~ "rhs");
    }
    else static if (hasMember!(Hook, "onOverflow"))
    {
        bool overflow;
        auto r = opChecked!op(payload, rhs, overflow);
        if (overflow) r = hook.onOverflow!op(payload, rhs);
        return Result(r);
    }
    else
    {
        // Default is built-in behavior
        return Result(mixin("payload" ~ op ~ "rhs"));
    }
}
```

That's pretty concise. Though I'm not sure why we have the separate overloads based on `const`{:.language-cpp}-ness. How would we do this stuff in C++? 

I'm hoping [P0847](https://wg21.link/p0847) gets adopted, so that I would write a very small mixin type that mimics the D language behavior:

```cpp
#define FWD(...) static_cast<decltype(__VA_ARGS__)&&>(__VA_ARGS__)
#define RETURNS(...) \
    -> decltype(__VA_ARGS__) { return __VA_ARGS__; }

struct dlang_operator_mixin {
    template <typename Self, typename T>
    auto operator+(this Self&& self, T&& rhs)
        RETURNS(FWD(self).opBinary(std::plus{}, FWD(rhs)))
        
    template <typename Self, typename T>
    auto operator-(this Self&& self, T&& rhs)
        RETURNS(FWD(self).opBinary(std::minus{}, FWD(rhs)))
        
    // ...
};
```

Note that instead of passing in names of operators, I'm passing in actual functions that themselves invoke the appropriate operations. And once we have them all in once place, `Checked<T, Hook>`{:.language-cpp} just inherits from that and provides `opBinary()`{:.language-cpp} equivalently to D as follows:

```cpp
template <typename F, Numeric Rhs>
    requires Invocable<F, T, Rhs>
auto opBinary(F op, Rhs rhs) const
{
    using R = std::invoke_result_t<F, T, Rhs>;
    using Result = std::conditional_t<
        Integral<R>, Checked<R, Hook>, R>;

    if constexpr (requires { hook.hookOpBinary(op, payload, rhs) })
    {
        auto r = hook.hookOpBinary(op, payload, rhs);
        return Checked<decltype(r), Hook>(r);
    }
    else if constexpr (Same<Bool, Rhs>)
    {
        return op(*this, static_cast<uint8_t>(rhs));
    }
    else if constexpr (FloatingPoint<Rhs>)
    {
        return op(payload, rhs);
    }
    else if constexpr (requires {
        hook.onOverflow(op, payload, rhs)})
    {
        bool overflow;
        auto r = opChecked(op, payload, rhs, overflow);
        if (overflow) r = hook.onOverflow(op, payload, rhs);
        return Result(r);
    }
    else
    {
        // Default is built-in behavior
        return Result(op(payload, rhs));
    }
}
```

Basically the same again, cool. Actual to my mind this is quite a bit better - I can use actual types and functions and traits instead of just sticking strings together.

### Conclusion

There are a few things that D's approach to Design by Introspection via `static if`{:.language-d} does better than we can do in C++. It's clearly superior at manipulating members conditionally. It's a lot less typing to do ad hoc introspection by name. You only need to learn one feature - `if`{:.language-d} - and use it in every place that you might want conditional code. In C++, we have `requires`{:.language-cpp} or named concepts in some places, `if constexpr`{:.language-cpp} in others, `[[no_unique_address]]` or traits in yet others. The amount of things you have to know in C++ is arguably a bit larger. 

But most of the differences between the D code in `Checked` and the C++20 equivalents I'm presenting here are basically just... spelling. In a couple spots, the bare minimum of gymnastics. 

And maybe we decide that it's worth having a real way to spell conditional members in C++, and maybe that way is something like:

```cpp
iterator_t<V> current_ requires !ForwardRange<V>
    = iterator_t<V>();
```

But I'm not convinced it's a big problem, and I'm _especially_ not convinced that it's such a drastically big problem that it necessitates redesigning `if constexpr`{:.language-cpp} to avoid introducing a scope. It seems like we already have the tools for this problem. If anything, I'd rather see a "Down with `template`{:.language-cpp}!" paper so I don't have to write this `hook.template opCast<U>`{:.language-cpp} nonsense any more.

Maybe the Next Big Thing is already here?
