---
title: "Rust vs C++ Formatting"
category: c++
tags:
  - c++
  - c++23
  - rust
  - formatting
---

In Rust, if I want to print some 32-bit unsigned value in hex, with the leading `0x`, padded out with zeros, I would write that as:

```rust
println!("{:#010x}", value);
```

In C++23, if I want to do the same, that's:

```cpp
std::println("{:#010x}", value);
```

The only difference is the spelling of the name of the thing we're calling (which is a function template in C++ and a macro in Rust) - otherwise, identical.

Nevertheless, there is a surprisingly vast gulf of difference between the two languages in how they handle formatting, at basically every level beneath the user-facing syntax. I thought the differences were pretty interesting and worth going over.

# Ergonomic Features

Before I go over the differences in the two format libraries, it's worth starting out by discussing the differences in _ergonomic features_ that are available to users. By an ergonomic feature, what I mean is a feature that doesn't necessarily add any functionality -- it may solve a problem that may otherwise have been solvable -- but rather that it makes it easier to get done, with less typing, and thus probably with fewer bugs.

The canonical example in C++ of an ergonomic feature might be: lambdas. We could always write function objects by declaring a class or class template somewhere and overloading its `operator()` - but doing so is very verbose and, if the call operator needs to be a template, it can't be written locally. Lambdas don't add functionality, but they are tremendously more user-friendly [^lambda].

[^lambda]: Even if I wish they were much terser.

When it comes to formatting, Rust has two major ergonomic features that have tremendous impact on user experience: `#[derive(Debug)]`{:.language-rust} and f-strings.



## `#[derive(Debug)]`{:.language-rust}

Rust has multiple different formatting traits (which I'll get into later), but for now I'll touch on the distinction between the two most important ones: `fmt::Display` and `fmt::Debug`. `Debug` is, as the name suggests, for debugging purposes and the [Rust documentation](https://doc.rust-lang.org/std/fmt/index.html#fmtdisplay-vs-fmtdebug) states that:

> `fmt::Debug` implementations should be implemented for all public types. Output will typically represent the internal state as faithfully as possible. The purpose of the `Debug` trait is to facilitate debugging Rust code. In most cases, using `#[derive(Debug)]`{:.language-rust} is sufficient and recommended.

Now, the notion of making your types printable for debug purposes is hardly unique to Rust. I do this in C++ all the time. But the key feature in Rust is how much code you have to write to accomplish this:

```rust
#[derive(Debug)]
struct Point {
    x: i32,
    y: i32,
}

fn main() {
    println!("p={:?}", Point { x : 1, y : 2});
}
```

Which, when run, prints:

```console
p=Point { x: 1, y: 2 }
```

The fact that you have to write one line of code to achieve this is tremendous. And even calling this one line is a bit much, since you'll typically be deriving many traits (like `Eq` or `Ord` or `Clone`, for a type like this), so we're effectively just talking about a few characters.

Of course, you _could_ implement the `Debug` trait by hand - it's not impossible without `#[derive]`{:.language-rust}. But over the long run, the ability to do this just adds so much value.

## f-strings

In the intro, I showed that in Rust you could write this:

```rust
println!("{:#010x}", value);
```

But recently (as of Rust 1.58), Rust also added the ability to use f-strings (also called interpolated literals or interpolated strings in some other languages), which allows you to just write:

```rust
println!("{value:#010x}");
```

In Rust, this was originally implemented (as far as I'm aware) in the [fstrings crate](https://crates.io/crates/fstrings), modeled after the Python feature of the same name. This feature exists in a number of other languages (as noted in the [Rust RFC](https://rust-lang.github.io/rfcs/2795-format-args-implicit-identifiers.html#other-languages)): JavaScript, C#, VB, Swift, Ruby, Scala, Perl, and PHP. There are certainly more (like Kotlin).

For a simple example like this, using string interpolation doesn't really make a big difference. Sure, it's _shorter_, but only by two characters, which is hardly significant. The value of the feature isn't how much typing it saves - the value here is that it allows you to put the variables you're formatting in the location that they're being formatted. Compare the readability between these two lines:

```rust
println!("Point is at (x={}, y={}, z={})", p.x, p.y, p.z);
println!("Point is at (x={p.x}, y={p.y}, z={p.z})");
```

It is much easier to understand what's being formatted in the second line and, importantly, it's easier to ensure that you format all of your arguments in the correct order - since seeing `"y={p.z}"`{:.language-rust} is clearly wrong.

As with `#[derive]`{:.language-rust}, f-strings don't add any functionality - these two lines really do the same thing. But this is the kind of language feature that once you start using regularly in one language (in my case, Python), you really want to use it everywhere, all at once.

See also David Sankel's [Rust Features That I Want In C++](https://www.youtube.com/watch?v=cWSh4ZxAr7E&t=1264s) from CppNow 2022.

# Format String Basics

Now that I got the ergonomics out of the way, let's talk about the way format strings work - whether in Rust or Python or C++ or a number of other languages. I'm going to use the terms in the C++ grammar for format strings, since that's what I'm most familiar with.

Given a string like:

```cpp
"A string literal with x={} and y={:#08x} and name={:>25}"
```

What we have are alternating string pieces and replacement fields. Each replacement field consumes one or more trailing (ignoring interpolation) arguments that are passed into the formatting function (or macro). A replacement field is enclosed in braces - the `{}`, `{:#08x}` and `{:>25}` above are all replacement fields.

A replacement field consists of an optional argument id followed by an optional format specifier. An argument id allows you to explicitly choose an argument by number (`{}` will replace with whatever the next argument is, while `{0}` will explicitly replace with the first argument). In C++ and Python, you cannot mix and match automatic and manual numbering. Manual numbering allows you to format the same argument multiple times, or to format the arguments out of order - which is particularly useful for translation purposes. The format specifier is what tells the library how to specifically format the chosen argument. The format specifier [^spec] must be introduced by a `:`.

[^spec]: Technically, [in C++](https://eel.is/c++draft/format.string.general), a _`replacement-field`_ is an optional _`arg-id`_ followed by an optional _`format-specifier`_, where a _`format-specifier`_ is a `:` followed by a _`format-spec`_. But while this makes sense grammatically, it's a bit awkward in English to have "format specifier" and "format spec" be these subtly different things, so I'm going to (hopefully not super confusingly) use "format specifier" to refer to the stuff after the colon, which I think colloquially is how people actually think about this.

Types typically have a common set of format specifiers they can use:

* fill and alignment
* sign
* width
* precision
* alternate type representation (e.g. hex for integers, or scientific for floating point)

For more details on what these specifiers are and how to use them, check out the [C++ fmt docs](https://fmt.dev/latest/syntax.html) or the [Rust docs](https://doc.rust-lang.org/std/fmt/) or the [Python docs](https://docs.python.org/3/library/string.html)

The good news here is that the way format strings work in Rust, Python, and C++ are _mostly_ the same.

One interesting distinction I do want to point out is how these languages differ in their handling of dynamic width. In all three, if I want to format a string, right-aligned, in a 25-character wide field, that's something like this:

```cpp
format("{:>25}", s)
```
But if I want the width to come from a variable instead, I can use this in C++ (or the equivalent in Python):

```cpp
format("{:>{}}", s, 25)
```

But Rust doesn't let you do `{}` (i.e. automatic numbering) for dynamic width , you can only provide an explicit index or a named variable -- which then must be suffixed with `$`. Rust's version is:

```rust
println!("{:>1$}", "hello", 25);
```

> Rust here allows a mix of automatic (for the string) and manual (for the width) indexing. Neither C++ nor Python allow this - you can write either `{0:>{1}}` or `{:>{}}` in those two languages, but not `{:>{1}}` or `{0:>{}}`.
{:.prompt-info}

I'm not sure why Rust differs here - I think the visual distinction between `{:>25}` and `{:>{}}` is quite a bit larger than `{:>25}` and `{:>1$}`, since the latter seems like it could easily be misread to be a width of `1`.

# C++ Formatting with `{fmt}`

Let's talk about the way the core C++ formatting library works -- with `{fmt}` and now `std::format`. How do you implement formatting for your type?

In C++, you have to specialize the type `fmt::formatter` (now `std::formatter`) and provide two functions for it: `parse()` and `format()`.

Using a two-dimensional `Point` example:

```cpp
struct Point {
    int x;
    int y;
};

template <>
struct std::formatter<Point> {
    constexpr auto parse(auto& ctx) {
        // ...
    }

    auto format(Point const& p, auto& ctx) const {
        // ...
    }
};
```

The job of `parse()` is to parse and validate the provided format specifier. It should throw an exception (`format_error`) if the provided format specifier is invalid. The `ctx` argument gives you access to the format string. What does it mean for a format specifier to be invalid for `Point`? Interesting question.

The job of `format()` is to use the saved state from `parse()` (if any) to format the object (`p`) into the provided output iterator (which you get via `ctx.out()`).

The simplest implementation would be to mandate that no format specifier is provided and then format the `Point` in some friendly, readable way:

```cpp
template <>
struct std::formatter<Point> {
    constexpr auto parse(auto& ctx) {
        return ctx.begin();
    }

    auto format(Point const& p, auto& ctx) const {
        return std::format_to(ctx.out(), "(x={}, y={})", p.x, p.y);
    }
};
```

## Using the standard specifiers

Let's say we don't want to just format `p.x` and `p.y` as regular integers, but also want to support whatever arbitrary format specifiers the ints do: padding, hex, etc. We can do that by deferring to `formatter<int>` for both the parsing and the formatting logic:

```cpp
template <>
struct fmt::formatter<Point> {
    fmt::formatter<int> f;

    constexpr auto parse(auto& ctx) {
        return f.parse(ctx);
    }

    auto format(Point const& p, auto& ctx) const {
        auto out = fmt::format_to(ctx.out(), "(x=");
        ctx.advance_to(out);
        out = f.format(p.x, ctx);
        out = fmt::format_to(out, ", y=");
        ctx.advance_to(out);
        out = f.format(p.y, ctx);
        *out++ = ')';
        return out;
    }
};
```

And with that, we can get arbitrarily complex formatting:

```cpp
fmt::print("{0}\n{0:#x}\n{0:*^7}\n", Point{.x=100, .y=200});
```

which prints:

```cpp
(x=100, y=200)
(x=0x64, y=0xc8)
(x=**100**, y=**200**)
```

The implementation is mildly tedious because we *have* to do this two-step:

```cpp
ctx.advance_to(out);
out = f.format(p.x, ctx);
```

Perhaps a different way of writing it it that's potentially less error prone would be to not even have a local variable for the output iterator:

```cpp
auto format(Point const& p, auto& ctx) const {
    ctx.advance_to(fmt::format_to(ctx.out(), "(x="));
    ctx.advance_to(f.format(p.x, ctx));
    ctx.advance_to(fmt::format_to(ctx.out(), ", y="));
    ctx.advance_to(f.format(p.y, ctx));
    return fmt::format_to(ctx.out(), ")");
}
```

This is because in the C++ model, the format context just has some arbitrary output iterator while the `format()` function on the `formatter` takes the format context - these two things need to be kept in sync. If we don't remember to `ctx.advance_to(out)` and `out` happens to be something like `char*`, then we would just overwrite stuff that we'd already written.

> It's hard to really ensure that you did this right because the default iterator in `{fmt}` is `fmt::appender`, with which you simply cannot run into this problem. It's just a `std::back_insert_iterator` - the kind of output iterator where `++it` doesn't actually do anything since it doesn't have a notion of position [^output]. Since all `std::back_insert_iterator<Container>`s into a given `Container` have the same state, forgetting to update with `advance_to` doesn't matter.
>
> Because `{fmt}` (and `std::format`) type-erases the provided output iterator, even if you use `fmt::format_to(out, "{}", p)` where `out` is a `char*`, this still won't break if you forget the `ctx.advance_to(out)`. This issue will _only_ surface in the library if you use _both_ compile-time format strings _and_ provide your own iterator:
>
> ```cpp
> char buf[300] = {};
> // without the calls to advance_to(), this will end up writing
> // just "2)" instead of "(x=1, y=2)", but buf[2:3] will still be "y="
> char* o = fmt::format_to(buf, FMT_COMPILE("{}"), Point{1, 2});
> ```
>
> You can see the impact of the missing `advance_to` call [here](https://godbolt.org/z/qPcqqfvxh).
{:.prompt-info}

> And that still isn't even completely right. Output iterators in C++20 are allowed to be move-only, so `ctx.advance_to(out)` might not compile. Like I said, it's hard to get this right.
{:.prompt-info}

[^output]: For those output iterators that aren't already input iterators, I think the output iterator API is a bit lacking, and I go over this in more detail in my [output iterators post]({% post_url 2022-02-06-output-iterators %})

Outside of remembering this pitfall, this is pretty nifty. We get support for all of this logic in one go.

## Using custom specifiers

We're not limited to just supporting the standard specifiers -- we can also add our own. Let's say that instead of supporting the standard integer specifiers, all we care about for our `Point` type is printing it either in cartesian coordinates, as `(x={}, y={})`, or in polar coordinates, as `(r={}, theta={})`.

I go over this in more detail in my CppCon 2022 talk, "The Surprising Complexity of Formatting Ranges," but say we wanted to use the `c` or `r` specifiers (for cartesian or rectangular) to format `x`/`y` and to use the `p` specifier (for polar) to format `r`/`theta`. We can implement that [this way](https://godbolt.org/z/EaPeq4e8E):

```cpp
template <>
struct fmt::formatter<Point> {
    // store additional state during parse()
    enum class Coord {
        cartesian,
        polar
    };
    Coord type = Coord::cartesian;

    constexpr auto parse(auto& ctx) {
        auto it = ctx.begin();
        // if we don't have any specifier, then we're done
        if (it == ctx.end() or *it == '}') {
            return it;
        }

        // otherwise consume the one character that we expect
        switch (*it++) {
        case 'r':
        case 'c':
            type = Coord::cartesian;
            break;
        case 'p':
            type = Coord::polar;
            break;
        default:
            throw fmt::format_error("invalid specifier");
        }
        return it;
    }

    auto format(Point const& p, auto& ctx) const {
        // our choice of output is based on our state
        if (type == Coord::cartesian) {
            return fmt::format_to(ctx.out(), "(x={}, y={})", p.x, p.y);
        } else {
            return fmt::format_to(ctx.out(), "(r={:.4}, theta={:.4})", p.r(), p.theta());
        }
    }
};
```

In my CppCon talk, I also go over some more complicated things that you can do with specifiers - like how to implement support for dynamic width that I mentioned earlier.

# Rust Formatting with `std::fmt`

In Rust, implementing manual formatting for `Point` looks quite different. There, you have to implement the trait `Display`, which only has one function for you to implement instead of two. The same, simplest-possible implementation for `Point` would look like this:

```rust
impl fmt::Display for Point {
    fn fmt(&self, formatter : &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "(x={}, y={})", self.x, self.y)
    }
}
```

`&self` here is the reference to `Point`, while `formatter` holds a similar role to the `ctx` arguments that were passed to `parse()` and `format()` in C++.

While this implementation looks superficially similar to the C++ implementation, just being a little shorter as we only had to write one function instead of two, they're actually quite different.

## The `Formatter` object

Let's start by going over `fmt::Formatter`. You can find the docs [here](https://doc.rust-lang.org/std/fmt/struct.Formatter.html).

In C++, `parse()` and `format()` are exposed to the user - to do with as they wish. In Rust, you only get `format()` (spelled `fmt`) - the library itself does the parsing for you, and gives you the state in the `Formatter` object.

That state looks [like so](https://doc.rust-lang.org/src/core/fmt/mod.rs.html#222-230):

```rust
pub struct Formatter<'a> {
    flags: u32,
    fill: char,
    align: rt::v1::Alignment,
    width: Option<usize>,
    precision: Option<usize>,

    buf: &'a mut (dyn Write + 'a),
}
```

The `flags` here includes the sign choice and whether we're using the alternative formatting, the other fields are not surprising. `buf` is an arbitrary type-erased buffer, similar to the way that `{fmt}` type-erases the output iterator [^dyn].

[^dyn]: The fact that you can just write `&dyn Write` to get the language to give you a non-owning type-erased object (this is like `std::function_ref`, not `std::function`) in Rust is simply spectacular.

Conceptually, you can think of Rust's `fmt::Display::fmt()` for `T` and C++'s `formatter<T>::format()` as being fairly equivalent. They even get the same pieces of information:

|Information|C++|Rust|
|-|-|-|
|the `T`|passed as first parameter|`&self`|
|the parse state|the `*this` object, populated from `parse()`|the `Formatter` object, populated by library|
|the output buffer|`ctx.out()`|`formatter.buf`|

Because `Display::fmt` takes a `Formatter`, the right way to extend our formatter for `Point` to support the standard specifiers is to pass the `Formatter` we get into subsequent calls to `fmt`:

```rust
impl fmt::Display for Point {
    fn fmt(&self, f : &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("(x=")?;
        fmt::Display::fmt(&self.x, f)?;
        f.write_str(", y=")?;
        fmt::Display::fmt(&self.y, f)?;
        f.write_str(")")
    }
}
```

> Note the use of `?` for error propagation, which I'd love to have in C++. I'm currently pursing this as [P2561](https://wg21.link/p2561)
{:.prompt-info}

This has the same structure as the C++ implementation - we have one mechanism to write the string pieces (in this case `f.write_str`) and a different mechanism to format the underlying part (in this calling `fmt::Display::fmt` again). But that formatting is handled internally in a way that ends up being more convenient for the user. No manual buffer manipulation here.

With that change, we have parity with our C++ implementation for the standard specifiers:

```rust
let p = Point { x: 100, y: 200 };
println!("{}", p);      // (x=100, y=200)
println!("{:*^7}", p);  // (x=**100**, y=**200**)
println!("{:#x}", p);   // error
```

Well... we almost have parity.

## A Constellation of Traits

The error we get from the above call is:

```console
error[E0277]: the trait bound `Point: LowerHex` is not satisfied
  --> src/main.rs:22:23
   |
22 |     println!("{:#x}", p);
   |                       ^ the trait `LowerHex` is not implemented for `Point`
   |
   = help: the following other types implement trait `LowerHex`:
             &T
             &mut T
             NonZeroI128
             NonZeroI16
             NonZeroI32
             NonZeroI64
             NonZeroI8
             NonZeroIsize
           and 21 others
note: required by a bound in `ArgumentV1::<'a>::new_lower_hex`
   = note: this error originates in the macro `$crate::format_args_nl` which comes from the expansion of the macro `arg_new` (in Nightly builds, run with -Z macro-backtrace for more info)

For more information about this error, try `rustc --explain E0277`.
error: could not compile `playground` due to previous error
```

The key really is just the first line. `{}` and `{:*^7}` require `fmt::Display`, but `{:x}` (and `{:#x}`, etc.) don't go through `fmt::Display`. They instead go through an entirely different, unrelated trait: `fmt::LowerHex`.

As the name implies, there's not just `fmt::LowerHex` for `x`. There's also `fmt::UpperHex` for `X`. And even that's not all of them. In total, there are [_nine_ formatting traits](https://doc.rust-lang.org/std/fmt/index.html#traits):

|Trait|Kind|
|-|-|
|`Binary`|`b`|
|`Debug`|`?`|
|`Display`|other|
|`LowerExp`|`e`|
|`LowerHex`|`x`|
|`Octal`|`o`|
|`Pointer`|`p`|
|`UpperExp`|`E`|
|`UpperHex`|`X`|

What this means is that - if we wanted to support printing `Point` in all the different ways that you can print an `i32`, we need to implement nine traits. Which all would look exactly the same as what I showed for `Display`, just substituting the name `Display` for all the other names.

The one odd exception is that implementing `Debug` doesn't just give you `{:?}` but also `{:x?}` and `{:X?}` (but that's it - so you can do debug hex, but not debug exponent?). I'm not sure why that's the case.

## Using custom specifiers

With C++, implementing a `formatter` for `T` requires writing a `parse()` function. That `parse()` gets, basically, a `std::string_view` and can interpret its contents however it wants.

With Rust, implementing any of the formatting traits (let's just stick with `Display`) requires just writing `fmt`, and you get the parsed specifiers ready-made for use. That `fmt::Formatter` object is what you get. Full stop. Which is quite nice when that's what you want, but there's no way to get anything else.

The Rust docs have this example:

```rust
use std::fmt;

#[derive(Debug)]
struct Vector2D {
    x: isize,
    y: isize,
}

impl fmt::Display for Vector2D {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        // The `f` value implements the `Write` trait, which is what the
        // write! macro is expecting. Note that this formatting ignores the
        // various flags provided to format strings.
        write!(f, "({}, {})", self.x, self.y)
    }
}

// Different traits allow different forms of output of a type. The meaning
// of this format is to print the magnitude of a vector.
impl fmt::Binary for Vector2D {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        let magnitude = (self.x * self.x + self.y * self.y) as f64;
        let magnitude = magnitude.sqrt();

        // Respect the formatting flags by using the helper method
        // `pad_integral` on the Formatter object. See the method
        // documentation for details, and the function `pad` can be used
        // to pad strings.
        let decimals = f.precision().unwrap_or(3);
        let string = format!("{:.*}", decimals, magnitude);
        f.pad_integral(true, "", &string)
    }
}

fn main() {
    let myvector = Vector2D { x: 3, y: 4 };

    println!("{myvector}");       // => "(3, 4)"
    println!("{myvector:?}");     // => "Vector2D {x: 3, y:4}"
    println!("{myvector:10.3b}"); // => "     5.000"
}
```

The example demonstrates different format specifiers producing very different kinds of outputs:

* `{}` goes through `Display`, and just prints `(x, y)`
* `{:?}` goes through `Debug`, which is `#[derive]`{:.language-rust}-ed, so you get the type name and then all the members
* `{:b}` goes through `Binary` which... prints the magnitude. Because `b` for... bagnitude?

The example also ends up demonstrating the limitation of having _only_ standard specifiers. That's simply all that you have available to you, so you have to pick from what's there.

In C++, I showed how you can have a `Point` that's printed either `c`artesian or `p`olar, by providing that specifier, which is fairly straightforward to implement. In Rust, we can use 'p' (that's `fmt::Pointer`) but you can't use either `c` or `r` - those letters just aren't available to you.

There _is_ technically the ability to use an arbitrary character, but only with alignment. That is:

```rust
impl fmt::Display for Point {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match f.align().map(|_a| f.fill()).unwrap_or('c') {
            'c' | 'r' => {
                write!(f, "(x={}, y={})", self.x, self.y)
            }
            'p' => {
                write!(f, "(r={:.4}, theta={:.4})", self.r(), self.theta())
            }
            _ => Err(fmt::Error),
        }
    }
}

fn main() {
    let p = Point { x: 100, y: 200 };
    println!("{:c^}", p); // (x=100, y=200)
    println!("{:p^}", p); // (r=223.6068, theta=1.1071)
}
```

This... [works](https://play.rust-lang.org/?version=stable&mode=debug&edition=2021&gist=7873478a36ae8efd642fd0654f028b7a), but just seems like an especially weird way to do this, and is highly limited anyway.

I used the `f.align().map(...)` approach above with the goal of parity with the C++ implementation: by default, the format is cartesian. Otherwise, the only allowed characters are `c`, `r`, and `p`. If I just checked `f.fill()`, the default value is a space. But if I matched on space or `c` or `r`, I would allow `{: ^}`, which I don't want to.

Maybe that's not a big deal, since I doubt anybody writes this sort of thing anyway.

# Comparing The Two Models

Now that we've seen a brief introduction to the C++ and Rust formatting models, we can start to meaningfully compare the two.

## A simpler model

In Rust, if we stick with the subset of standard specifiers supported by `Formatter` (basically: fill, align, width, precision, sign), then the Rust approach lets you do a lot of things easier. Because the buffer writing is hidden from you, you don't have to worry about the keeping the writing in sync - the implementation of `Display` for `Point` supporting these specifiers is shorter than the C++ one.

The other notable advantage of Rust's `fmt::Formatter` is that it provides a lot of helper functions to get the various specifier state out and to use it. The `Formatter` will tell you the fill, the alignment, the width, the precision, the sign. And it has member functions to help you write things padded.

In C++, whether in `{fmt}` or the standard library, there are no such helpers. You can use `fmt::formatter<int>`, as I did above, to be able to do more complex formatting - but the only members that type exposes are `parse()` and `format()`. So if you want to support these specifiers yourself, you kind of just have to implement all of that logic... yourself.

## Chrono

On the other hand, the custom specifier support allows for a lot more functionality to be handled by the formatting library itself. Let's say I want to print today's date in UTC. I can do that:

```cpp
std::println("Today is {:%Y-%m-%d}", std::chrono::system_clock::now());
```

Chrono basically has its own mini-language of placeholders that you can use to build up its format specifier. That is pretty cool, and very useful. You can't do that in Rust - since there's no notion of custom specifier at all, and something this complicated you can't just hack into the fill character.

Rust also has a chrono library, which gives you time points that are printable:

```rust
let now = chrono::offset::Utc::now();
println!("{}", now);    // 2023-01-02 03:18:57.477157070 UTC
println!("{:?}", now);  // 2023-01-02T03:18:57.477157070Z
```

Rust's chrono crate _does_ support this sort of arbitrary placeholder logic that C++ does, and with the same placeholder syntax too. It's just that you have to do it differently:

```rust
let now = chrono::offset::Utc::now();
println!("Today is {}", now.format("%Y-%m-%d")); // Today is 2023-01-02
```

This works, and is fine for this simple example. But it doesn't scale particularly well. Since what happens when we move up to more complex structures. Like...

## Ranges

Rust has a very different philosophy for formatting ranges than C++ does.

In C++, if I try to print a container and then an adapted version of it:

```cpp
auto v = std::vector{1, 2, 3, 4, 5};
std::println("{}", v);
std::println("{}",
    v | std::views::transform([](int i){
        return i * i;
    }));
```

That prints:

```console
[1, 2, 3, 4, 5]
[1, 4, 9, 16, 25]
```

Which, I think, is probably what most people want and expect. But Rust's approach here is quite different:

```rust
let v = vec![1, 2, 3, 4, 5];
println!("{:?}", v);
println!("{:?}", v.iter().map(|i| i * i));
```

That, instead, prints:

```console
[1, 2, 3, 4, 5]
Map { iter: Iter([1, 2, 3, 4, 5]) }
```

> Neither `Vec<T>` nor any of the iterators implement `fmt::Display`, only `fmt::Debug`.
{:.prompt-info}


I quoted from the Rust documentation earlier that, for `fmt::Debug`:

> Output will typically represent the internal state as faithfully as possible.

So the goal of `Debug` for `Map` isn't necessarily to print the elements that you get out - it's to represent the internal state of the `Map` itself. That does make sense on some level.

But `Map` doesn't implement `fmt::Display`. None of these types do. So what do I do if I did want the `[1, 4, 9, 16, 25]` output that I get out of the box in C++? There's actually no solution in the Rust standard library. We instead of have to turn to the [`itertools` create](https://docs.rs/itertools/latest/itertools/) to add some extensions for us:

```rust
println!("[{}]", v.iter().map(|i| i * i).format(", "));
```

The `format` function (on the `Itertools` trait) basically returns some new type that itself implements `fmt::Display`, using the specifier to print each element and the provided string as the delimiter.

Now, if I want to format the elements of a range differently from just `{}`, I can do that in both Rust and C++:

```cpp
std::println("{::*^5}", v);
```

vs

```rust
println!("[{:*^5}]", v.iter().format(", "));
```

Both of these print:

```console
[**1**, **2**, **3**, **4**, **5**]
```

Though we get there in wildly different ways. In C++, the `formatter` for ranges uses the underlying type's `formatter` to parse the element-specific format specifier (after the second colon), and we use that `formatter` to print every element. In Rust, the `format()` hook returns a new object which implements `Display` by using the provided `Formatter` to `fmt` each element, separated by the provided delimiter.

Now here's the question: what if I had a range of dates, and I wanted to print them all with the `%Y-%m-%d` format? In C++, that's exactly the same idea as the previous example: we're just providing the format specifier we want to use for each element:

```cpp
std::println("{::%Y-%m-%d}", dates);
```

But in Rust, for the chrono time point, this isn't a format specifier. We had to do this whole other function call to get that behavior. So we need a new mechanism to solve this problem. The `itertools` crate provides this for us under the name `format_with`:

```rust
println!(
    "[{}]",
    dates
        .iter()
        .format_with(", ", |elt, f| f(&elt.format("%Y-%m-%d")))
);
```

`format_with` is the most general API and probably lets you do anything you want. But it's now fairly complicated, and differs quite a lot from the simple case. It may be helpful to place these examples back to back to make this more clear - in both cases, I'm formatting a range of some element type with some particular choice of specifier:

```cpp
// C++
std::println("{::*^5}", v);
std::println("{::%Y-%m-%d}", dates);
```

vs

```rust
// Rust
println!("[{:*^5}]", v.iter().format(", "));
println!(
    "[{}]",
    dates
        .iter()
        .format_with(", ", |elt, f| f(&elt.format("%Y-%m-%d")))
);
```

## Unsupported Specifiers

One other notable difference between the two is in their handling of unsupported specifiers. In the very first examples I showed for each language, I demonstrated how to format a `Point` as `(x=1, y=2)`. The Rust implementation was shorter, but the C++ one wasn't exactly a leviathan.

But the two implementations weren't exactly equivalent. The C++ approach _only_ supported that case. Attempting to use any other specifier would have been a compile error:

```cpp
std::println("{}", p);     // (x=1, y=2)
std::println("{:*^7}", p); // error
std::println("{:+}", p);   // error
```

But the Rust approach would allow and simply ignore any specifier that wasn't used in the implementation:

```rust
println!("{}", p);     // (x=1, y=2)
println!("{:*^7}", p); // (x=1, y=2)
println!("{:+}", p);   // (x=1, y=2)
```

The specifiers still have to be *valid* - Rust would still reject `{:7^*}`, the thing that I seemingly always want to type instead. But we didn't use any of specifiers the user provided in our implementation, so the output is the same.

Is it better to _reject_ unsupported specifiers, or _ignore_ unsupported specifiers? Good question.

## Debug Representation

In Rust, debug formatting is a first-class citizen via `fmt::Debug`. And, as I mentioned at the very top of this blog, it's extremely easy to opt into via `#[derive(Debug)]`{:.language-rust}.

In C++, debug formatting is also a thing, that notably surfaces in formatting ranges: formatting `"hello"s` prints `hello` but formatting `vector{"hello"s}` prints `["hello"]`. Notice the quotes: that comes from the debug representation. It's not just quoting, the string will also be escaped (e.g. newlines will be formatted as the two-character sequence `\n`).

But while in Rust, `?` is just a first-class specifier that everybody can rely on, that simply isn't the case in C++. Not all C++ types support debug formatting with `?`, and whether a type does or not is entirely up to that type author. `std::string` supports it, but `int` does not, for instance. Even worse than that, a type could support a `?` specifier whose meaning has nothing whatsoever to do with debugging (in the same way my `Point` example used `p` in a way that has nothing to do with pointers).

That's why in C++, I had to come up with a completely different mechanism for choosing the debug representation: an optional member function on `formatter` named `set_debug_format()`. And this design is still in flux, since originally this was a function that took no arguments, but it may need to change to take a `bool` (to enable or disable debug formatting). This would simply not be an issue we would have to think about if, in C++, we had any control over specifiers. But we don't. That's one of the downsides for allowing users to do anything they want: they can do anything they want.


# Conclusion

On the usage side, the C++ and Rust models of formatting look very similar. Nearly identical even. But they have a surprising amount of differences.

In Rust, `{:?}` always works for every type and is always some debug-friendly formatting. In C++, `?` isn't special at all, so types support it or not as they see fit. It works for `std::string`, but not `int`. Instead, we have a completely different approach to debug representation, which is still in flux.

In C++, each type can support whatever specifiers it wants. In Rust, there is one global fixed set of specifiers that is parsed by the implementation. This means that the Rust ecosystem is more consistent and coherent, since there's only one way of doing things. But it also means that the many times that custom specifiers would prove useful, Rust needs some ad hoc escape hatch, which is just a different kind of inconsistency. It also means that Rust users will just abuse other formatting traits to solve their customization needs (such as the docs themselves demonstrating using `Binary` to display a magnitude), so you can end up with choices of specifiers that make no sense.

In C++, writing wrappers that propagate all specifiers is mildly tedious due to needing to keep the context and output iterators in sync, but otherwise fairly straightforward. In Rust, this seems like it should be less tedious, since the formatter manages all of its state directly, except that you actually have to implement nine traits to do this, which seems... like an odd design decision to me.

In C++, the library doesn't provide any tools to help you parse things like fill, alignment, and width, so you have to implement them yourself. Which is not trivial. In Rust, you don't need a tool to parse the specifiers since you just get the result of the parse.

In C++, ranges are formattable. In Rust, iterators only implement `fmt::Debug` but in a way that logs their state, not the underlying elements. You need to include the `itertools` create to actually format ranges, but it ends up being a bit complicated due to the way that custom specifiers end up being handled.

Which approach is better? I think different people could react very differently to those paragraphs.

On the whole, I was surprised at how *different* Rust's and C++'s approaches ended up being to solving the same problem, and I thought it was interesting to really consider the the implications of them.

## Implementing Rust's approach with C++

As is usually the case with C++ [^models], you can implement the Rust model in C++, but you cannot implement the C++ model in Rust.

[^models]: My [CppNow 2021](https://www.youtube.com/watch?v=d3qY4dZ2r4w) and [CPPP 2021](https://www.youtube.com/watch?v=95uT0RhMGwA) talks compared, in part, the C++ iterator model to the Rust iterator model. The talk showed how you can implement a Rust iterator with a C++ iterator pair pretty easily, but that you can't do better than a C++ input iterator from a Rust iterator.

To implement the Rust model, you can write a general formatter object:

```cpp
struct GeneralFormatter {
    uint32_t flags;
    char fill;
    Alignment align;
    std::optional<size_t> width;
    std::optional<size_t> precision;

    constexpr auto parse(auto& ctx) {
        // I am not even going to try
    }

    template <typename T>
    auto format(auto& object, auto& ctx) const {
        // I am not even going to try
    }
};
```

And then just use that to implement all of your `parse()` functions and as your helper for all of your `format()` functions.

## Improving C++'s approach

There are a few things that make Rust's approach more user-friendly that I think we can, and should, pursue.

The biggest two, overwhelmingly, are the [ergonomic features](#ergonomic-features) I mentioned earlier. Static reflection will allow us to provide a `#[derive(Debug)]` equivalent and there is ongoing discussion about how to support interpolated literals in C++ for use with formatting.

One of the difficulties (though not the only one) with supporting interpolated literals is precisely this issue of custom specifiers. For instance, how do you make this work:

```cpp
std::println(f"{name:>{width}}");
```

Getting the `name` part is fine, but what do you do with `width`? If `name` happens to be a `std::string`, then `>{}` means right-aligned using the next format argument as the width. In which case `{width}` should be interpreted as interpolating `width` -- doing name lookup on `width` and evaluating it.

But if `name` is some other type, like an `acme::Widget`, then `>{width}` could mean _anything_. It _could_ be a dynamic width like `std::string` and `int` and so forth. Or it could be a placeholder syntax similar to chrono, where `>{width}` is a request to print the `Widget`'s `width`, having nothing to do with alignment whatsoever, and certainly not a request for a variable named `width`. Would interpolation need to be something the user can hook into, so that if they do support dynamic arguments, they can interpolate, otherwise they don't?

The other problem is that, for an arbitrary user-defined type, the format specifier does not need to be balanced between `{` and `}`. I mean, it _should_ be balanced, and it seems pretty hostile to try to come up with a reason to _not_ be balanced. But this is C++, so since you _can_, somebody certainly will. But at least in this case, we can just say that if you play silly games, you win silly prizes: no string interpolation for you. Come back next year with sane bracing.

Outside of these two language improvements, one of which really having nothing in particular to do with formatting, specifically, there are a few things that are probably worth thinking about:

* adding more member functions to `format_context` to make it more convenient to alternate between what kind of thing we're formatting, which would also make it less error prone. Perhaps (using Rust's names, as usual):
    ```cpp
    auto format(Point const& p, auto& ctx) const {
        return ctx.write_str("(x=")
                  .format(p.x, f)
                  .write_str(", y=")
                  .format(p.y, f)
                  .write_str(")")
                  .out();
    }
    ```
* adding something akin to the `GenericFormatter` type I showed earlier to make it easier for users to support common specifiers like padding.

To be clear, both of these combined I think provide significantly less value than string interpolation which itself provides significantly less value than static reflection. But I do think these would provide _some_ value, and I definitely think both are much easier problems to solve.

## Specifiers Are Useful

Outside of the significantly better ergonomics Rust provides, I do think C++'s general approach of allowing arbitrary specifiers is the better one. When used well (as in chrono or in range element formatting), it lets the user do a lot of complicated things quite concisely and consistently: the fact that formatting a range of dates and a range of integers looks the same is a big win.

The specifier mini-language does have the potential to turn into line noise very quickly, so it's certainly not a panacea. But on the whole I'd definitely rather have it than not.

---
