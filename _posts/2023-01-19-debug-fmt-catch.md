---
layout: post
title: "Debug Formatting, Catch2, and ODR"
category: c++
tags:
 - c++
 - formatting
pubdraft: true
---


At the beginning of this year, I wrote a post comparing [Rust and C++ formatting]({% post_url 2023-01-02-rust-cpp-format %}). One of the big differences between the two is that Rust has a standard way of doing _debug_ formatting (`Debug`), as distinct from its standard way of doing _display_ formatting (`Display` and a bunch of others). Python similarly also has such a distinction (`repr` vs `str`). Rust also provides a very easy way to opt-in to `Debug`, but the important part for the purposes of this post is that `Debug` exists. Not so in C++.

## Formattable Types in C++

C++ doesn't really have a notion of debug formatting at all. Up until C++20, the standard way of doing formatting was `operator<<`. Since C++20, we can specialize `std::formatter<T>` (or, until then, `fmt::formatter<T>`). That's our only real way of expressing formattability. A type is either streamable or not, formattable or not. There's no notion of kind.

As a result, lots of types in the standard library have no printing capability. `std::optional<T>`, `std::variant<Ts...>`, and `std::expected<T, E>` aren't printable (neither with iostreams nor with format). `std::tuple<Ts...>` and `std::vector<T>` will be formattable in C++23, but only if all of their underlying types are. For types like `std::optional<int>`, `std::tuple<std::optional<int>>`, or `std::vector<std::optional<int>>`, you get nothing.

This is pretty limiting, because the only entity that should really be adding formatting capabitility to standard library types is the standard library. If the standard library doesn't...

## Catch2 and Stringification

[Catch2](https://github.com/catchorg/Catch2) is a popular C++ unit testing library, which provides macros that let you both write straightforward expressions:

```cpp
CHECK(x == y);
```

and, especially nicely, also provide stringification of the components of the expression in case of failure:

```
example.cxx:7: FAILED:
  CHECK( x == y )
with expansion:
  1 == 2
```

This is quite nice for the programmer, since you get to see all the values right there.

I'm not going to get into how Catch2 decomposes the expressions in the test macros, but I am going to talk about how the formatting side of things. In particular: how does Catch2 format an argument when a test fails?

One approach might be to _require_ streaming. That is, require `Display`. This is a highly limiting approach, because lots and lots of types aren't streamable (e.g. `std::vector<int>` isn't, and won't be, streamable, even though in C++23 it will at least become formattable). Requiring streaming thus reduces too many checks to writing `CHECK(bool(a == b))` and getting no useful output.

A different start point (in C++20) might be to print _something_, even if the type isn't printable:

```cpp
template <typename T>
auto stringify(T const& value) -> std::string {
    if constexpr (requires { std::cout << value; }) {
        std::ostringstream oss;
        oss << value;
        return std::move(oss).str();
    } else {
        return "{?}";
    }
}
```

Streamable types are streamed, non-streamable types you just get `{?}`. This works fine for `int`, but we quickly find out that it's not... quite sufficient:

```
simple.cxx:19: FAILED:
  CHECK( '\n' == '\t' )
with expansion:


  ==

```

That's not what Catch2 actually prints when you run that check (but oddly is very close to what Catch2 prints when you do the same comparison with `std::string`s [^escaping]), which is a good thing, because that output doesn't actually help you figure out much of anything at all.

[^escaping]: By default, Catch2 just wraps the string in quotes - which at least helps figuring out spaces. If you pass `-i`, then it'll also escape newlines and tabs. This still isn't quite sufficient, as ideally every non-printable character, as well as quotation marks, are escaped. And without command-line help.

This is a good example of the distinction between display formatting and debug formatting: in display formatting, `'\n'` needs to print as a newline. That's what it is. But in debug formatting, you don't want to see a newline. If you're printing a `char` whose value is a newline, you want to see literally the four characters `'\n'`.

Catch2 recognizes this, and so it defines its stringification a bit differently [^different]:

[^different]: Not _exactly_ like this, I'm just modernizing the implementation a bit. But the details aren't particularly important here.

```cpp
template <typename T>
struct StringMaker;

template <typename T>
auto stringify(T const& value) -> std::string {
    return StringMaker<T>::convert(value);
}

// the primary specialization, by default, tries to stream the type if possible
// otherwise falls back to just doing {?}, since can't do much else
template <typename T>
struct StringMaker {
    static auto convert(T const& value) -> std::string {
        if constexpr (requires { std::cout << value; }) {
            std::ostringstream oss;
            oss << value;
            return std::move(oss).str();
        } else {
            return "{?}";
        }
    }
}

// and then there are a whole bunch of specializations for standard library
// types to do more useful debug formatting
template <> struct StringMaker<std::string> { /* ... */ };
template <> struct StringMaker<std::string_view> { /* ... */ };
template <> struct StringMaker<char const*> { /* ... */ };
template <> struct StringMaker<char*> { /* ... */ };
template <size_t N> struct StringMaker<char const[N]> { /* ... */ };
template <size_t N> struct StringMaker<char[N]> { /* ... */ };
// ... etc. ...
```

This approach allows Catch2's test output to be much more useful to the people running the test than the simpler display formatting would've allowed. Strings and characters can be printed escaped. There's a bunch of extra logic in the library to do things like... floating point precision, or printing large numbers in hex, or actually formatting `std::byte`, and so forth.

Testing is a great example of the need for debug formatting, and `Catch::StringMaker<T>` is precisely that: a mechanism for providing debug formatting, as distinct from display formatting.

## Opting into Debug Formatting with Catch2

We have an implementation of `Optional<T>`, as I may have mentioned on occasion.

That type currently is streamable when `T` is streamable and formattable when `T` is formattable. But only in those cases. This, I think, is a fairly typical way people implement printing support for wrapper types.

Because Catch2, by default, uses the stream operator, this ends up working great in those situations when `T` is streamable and that stream format is useful in a testing context. Like, ints:

```
optional.cxx:142: FAILED:
  CHECK( opt == Optional<int>(17) )
with expansion:
  Some(32) == Some(17)
```

But, because it's using the underlying type's stream operator, this isn't great when it comes to characters. Sure, you can technically figure out what's going on in this output, but it's hardly ideal:

```
optional.cxx:157: FAILED:
  CHECK( Optional<char>('\n') == Optional<char>('\t') )
with expansion:
  Some(
  ) == Some(    )
```

And because it's relying on streamability, it gives zero information whatsoever for unprintable types:

```
optional.cxx:212: FAILED:
  CHECK( o1 == o2 )
with expansion:
  {?} == {?}
```

Now, for unprintable types, we obviously can't print them. That's kind of what unprintable means. But at least we could still provide _some_ information: namely we could distinguish between `Some({?})` and `None` (which, incidentally, was the test failure here).

As a result, for Catch2 testing with our `Optional`, it's not enough to provide a stream operator _even for streamable types_. We still need to provide debug formatting. Which Catch2 lets us do, by specializing `StringMaker`:

```cpp
namespace Catch {
template <typename T>
struct StringMaker<Optional<T>> {
    static auto convert(Optional<T> const& o) -> std::string {
        ReusableStringStream rss;
        if (o) {
            rss << "Some(" << Detail::stringify(*o) << ')';
        } else {
            rss << "None";
        }
        return rss.str();
    }
};
}
```

`ReusableStringStream` is a Catch2 thing to make this more efficient, which isn't relevant here. The important part is that when we print the value (the underlying `T`, if we have one), we don't just stream it to `rss`, we call `stringify`. That's shorthand for calling `StringMaker<T>::convert(*o)`, which is going to give us the debug formatting logic for `T`. If `T` isn't printable at all, then we'll get `Some({?})`, but that's fine - that's the best we could do anyway.

Importantly, we always recurse into calling `stringify`, never `<<` for the underlying types, to ensure that we get debug formatting all the way down.

Adding that specialization improves our error messages for our prior failing tests. Easier-to-understand values in the first case, actual information in the second:

```
optional.cxx:157: FAILED:
  CHECK( Optional<char>('\n') == Optional<char>('\t') )
with expansion:
  Some('\n') == Some('\t')

optional.cxx:212: FAILED:
  CHECK( o1 == o2 )
with expansion:
  Some({?}) == None
```

Debug printing is pretty cool.

## The One Definition Rule

Here's where we run into problems. In C++, we have the ~~Highlander~~ one definition rule (ODR): there can only be one definition of anything. One aspect of this is that a specialization of a template `C` for some parameter `T` has to pick the same specialization everywhere in the program, across all translation units.

That aspect is the subject of the C++ limerick (as found in [\[temp.expl.spec\]/8](https://eel.is/c++draft/temp.expl.spec#8.sentence-2)):

> When writing a specialization,<br>
> be careful about its location;<br>
> or to make it compile<br>
> will be such a trial<br>
> as to kindle its self-immolation.

And the particular template that is the subobject of this particular aspect of the one definition rule is the `stringify()` function template, which instantiates `StringMaker<T>`.

Now, let's say we do something like this:

* the main `Optional` implementation is in `<optional.h>`
* the `Catch::StringMaker` specialization is in `<catch_helpers.h>`

After all, most users of `Optional` won't be in unit tests, so we wouldn't want to just include Catch headers. So let's let the unit test users include the unit tests things explicitly, if that's what they want.

But this allows running into a situation like this:

```cpp
// TU #1
#include <catch.hpp> // or Catch2 v3 macros, doesn't matter
#include <optional.h>

// bunch of tests using Optional
```

```cpp
// TU #2
#include <catch.hpp>
#include <optional.h>
#include <catch_helpers.h>

// bunch of tests using Optional
```

That is: we have two unit test source files that have a bunch of `CHECK`s or `REQUIRE`s on `Optional`, but only one of those source files included the specialization `StringMaker<Optional<T>>`. Both source files compile - they just provide different definitions for, say, `stringify(Optional<char>)`, because they end up using different specializations of `StringMaker<Optional<char>>`. That is a violation of the one definition rule - which means that I don't even have a valid program.

The important thing to keep in mind here is that the primary template of `StringMaker<T>` is always available for all types. Worst case you just get `{?}`, but it's there. That's a big difference from iostreams or format. With those libraries, I could get away with providing dedicated headers, like `<optional_stream.h>` for `<<` and an `optional_fmt.h>` for the `formatter` specialization, since if users forgot to include them, their code would simply not compile.

But in this case, there _is_ a default. So you can't rely on a compiler error to remind you to reliably include `<catch_helpers.h>`. And if you forget to do so, you can run into this ODR issue.

In practice, the ODR violation is probably benign: both test source files will still print _something_ for the `Optional` values. It's just that either of the two files could end up using either of the two definitions. If both use the `StringMaker<Optional<char>>` specialization, great! If both use the `StringMaker<T>` primary template, then you're going to get worse output than ideal - which could be very confusing, especially if you have a test case failing in the source file that's actually providing the specialization. But at least, it's likely the worst case scenario here is simply confusion.

But that's still... less than great? I don't want to replace bad test case output with ODR violations, I wanted to replace bad test case output with _good_ test case output.

So how can I fix this?

## Where do you specialize `Catch::StringMaker<T>`?

If `Optional<T>` and `StringMaker<Optional<T>>` are declared in distinct header files (which is the most sensible way to declare them), that opens the door for ODR violations if you have multiple source files that both run tests using `Optional<T>` that don't all include the test header.

One solution, then, is to actually declare both in the same file. `StringMaker<T>` is just a simple class template - it can be forward-declared without bringing in all the other Catch2 machinery. We don't _need_ to use `ReusableStringStream`, we can just implement it this way:

```cpp
// the actual implementation
template <typename T>
struct Optional { ... };

namespace Catch {

template <typename T>
struct StringMaker;

template <typename T>
struct StringMaker<Optional<T>> {
    static auto convert(Optional<T> const& o) -> std::string {
        std::ostringstream oss;
        if (o) {
            oss << "Some(" << StringMaker<T>::convert(*o) << ')';
        } else {
            oss << "None";
        }
        return std::move(oss).str();
    }
};

}
```

This... works. It requires including `<string>` and `<sstream>`, which the `Optional` header didn't used to need, and pushing those additional includes onto all of our users. That doesn't seem particularly exciting. We could avoid the `<sstream>` include too, by just doing `return "Some(" + StringMaker<T>::convert(*o) + ")";` in the value case, for instance. So that's one approach.

A different approach would be to turn ODR violations into compile errors:

```cpp
// the actual implementation
template <typename T>
struct Optional { ... };

namespace Catch {

template <typename T>
struct StringMaker;

template <typename T>
struct StringMaker<Optional<T>>;

}
```

Here, we're again forward-declaring `Catch::StringMaker<T>`, but now instead of providing the full specialization for `StringMaker<Optional<T>>`, we're only declaring it. This ensures that any use of `StringMaker<Optional<T>>` without including the `<catch_helpers.h>` header where it's actually defined ends up being a compile error - because this template isn't defined yet. That's great, since any source file that has a compile error, you can add the include to, and then we get functional tests without ODR issues. But it would also break all of our users, who may or may not care about this issue - so we may want to wrap this in an opt-in macro.

But that's... kind of the extent of our options I think:

* push an extra include or two to all users, even if only a small percentage of those uses will be actual Catch2 test source files, not all of which will even end up needing to `stringify()` an `Optional`
* allow for pre-declaring this specialization so that users can include the `StringMaker<Optional<T>>` specialization if they want it, but helping ensure that they don't forget to _consistently_ include it everywhere

These are fairly underwhelming options. Especially since this `StringMaker` specialization only helps Catch2 users with tests that specifically check expressions whose types are `Optional`.

What if our users use [doctest](https://github.com/doctest/doctest), for instance? That framework _also_ has to address the issue of debug formatting, and does so in a similar way to Catch2. It's just that its mechanism is `doctest::StringMaker<T>` instead of `Catch::StringMaker<T>`. What if our users use [GoogleTest](https://github.com/google/googletest) instead? There, the customization point is a function called `PrintTo()`. Every test framework invents its own mechanism of doing debug formatting, because debug formatting is pretty important.

Do we need to provide all of these as well? All in different headers or all in the same header?

## Will Modules Save Us?

No.

While `std` being a module would at least alleviate the concerns of extra `<string>` or `<sstream>` includes, once `Catch2` is a module, then I'm not sure this is even possible. You can't forward-declare `Catch::StringMaker` and then later use it from the module - there's no way to indicate that a forward declaration is actually intended to be associated with some module [^proclaimed].

[^proclaimed]: There used to be such a thing as a _proclaimed-ownership-declaration_, but it was removed.

That would leave us with fairly poor choices.

Our implementation could `import Catch2;` so that we could provide these specializations, in the same way as described above that we just provide the specializations in the same header as the implementation. Which is basically saying that... we need to `import` every test framework that we want to provide debug formatting for?

Or our implementation could provide a _separate_ module for the Catch2 `StringMaker` specializations - which itself does `import Catch2;` This is the more sound approach, but it gets us back to the ODR issue since it's possible to have separate translation units use different specializations.

## Debug Formatting

The crux of the issue here is that we have customizable functionality that is defaultable - and you need to make sure that you consistently include the customizations.

That's a fairly general problem. But in this case, debug formatting is such a commonly needed functionality that its absence is pretty notable. I listed three test frameworks that each have their own mechanism of doing debug formatting.

I said something earlier that wasn't _entirely_ accurate. I said that C++ doesn't have a standard notion of debug formatting, but in C++23 we _kind of_ added one by way of adding support for [formatting ranges](https://wg21.link/p2286): when formatting a range or tuple of a type like `string` or `char`, we know we need to format those underlying `string`s or `char`s differently from their usual formatting - for all the same reasons that these test frameworks (and other programming languages) do. The approach there was to add a new, optional function to `formatter`:

```cpp
template <typename T, typename Char>
struct formatter {
    // mandatory
    formatter();

    // mandatory
    // must be constexpr to support format() and not just vformat()
    template <typename ParseContext>
    constexpr auto parse(ParseContext&) -> ParseContext::iterator;

    // mandatory, might need to take T& instead of T const&
    template <typename FormatContext>
    auto format(T const&, FormatContext&) const -> FormatContext::iterator;

    // optional
    constexpr void set_debug_format();
};
```

Notably, while types like `std::string` and `char` have this function, types like `int` do not.

There are currently a few ongoing conversations on `formatter` semantics:

* changing the library to allow omitting the call to `parse()` if there is no _`format-specifier`_ for a given argument ([P2733](https://wg21.link/p2733))
* changing the API to be `set_debug_format(bool )` to allow for enabling or disabling debug formatting, not simply enabling (which would be necessary if we make that first change)

I am wondering at this point if we shouldn't just take the opportunity to come up with a way to provide first-class debug formatting as part of the `formatter` API and make this the standard way of providing debug formatting.

The benefits of having standard debug formatting are pretty clear:

* everyone wouldn't have to reinvent a new way of doing this.
* it provides an easy answer to the question of where to provide those specializations.

Additionally, if there _were_ a standard debug formatting mechanism, then test frameworks wouldn't have to worry about providing _default_ formatting for not-otherwise-printable types. Because all types really should be debug-formattable, you could just require that (as Rust's assertions do require `Debug`). No ODR concern either.

Of course, there's just one small question: how do you do it?

## Approach 1: Dedicate `?`

One potential approach is to dedicate the `?` specifier to mean debug formatting. That is, we have the following rules:

1. If no _`format-specifier`_ is provided, then `formatter<T>::parse()` is not called, and `formatter<T>::format()` must have been provided. That will be the formatting function that is called.
2. Otherwise, if _`format-specifier`_ is provided, and its _`format-spec`_ is just `?`, then `formatter<T>::parse()` is not called and indeed `formatter<T>` need not have been specialized at all. Instead, `debug_formatter<T>::format()` must have been provided. That will be the formatting function that is called (I'll illustrate this below).
3. Lastly, if _`format-specifier`_ is provided and its not just `?`, then `formatter<T>::parse()` will be called as usual and then `formatter<T>::format()`.

Here, `debug_formatter` consists of a single function:

```cpp
template <typename T, typename Char>
struct debug_formatter {
    template <typename FormatContext>
    auto format(T const&, FormatContext&) const -> FormatContext::iterator;
};
```

Formatting for ranges and tuples will, by default, try to call the underlying type's `debug_formatter<T>::format()` (if it exists), otherwise will call the underlying type's `formatter<T>::format()` (as it does today). This is instead of doing the `set_debug_format()` logic that we currently have.

Standard library types will all provide `debug_formatter<T>::format()` - which for some types just calls `formatter<T>::format()` (like `int`) but for other types will juts produce some useful output, even if there is no `formatter<T>::format()` at all (like `std::optional<int>`). The standard library will also provide a `debug_formatter_memberwise<T, Char>` that will, with the help of reflection, implement debug formatting as simply iterating through the members and printing all their names and values.

An implementation for `Optional` that additionally supports arbitrary specifiers might then look like this:

```cpp
template <typename T>
    requires debug_formattable<T>
struct debug_formatter<Optional<T>> {
    auto format(Optional<T> const& v, auto& ctx) const {
        if (v) {
            return format_to(ctx.out(), "Some({:?})", *v);
        } else {
            return format_to(ctx.out(), "None");
        }
    }
};
```

So far so good. This is quite easy to provide, and easy enough to nest, since we simply reserve `?`.

The more interesting question is what do we do for `formatter<Optional<T>>`? What we have today looks like this: `Optional<T>` is formattable when `T` is, and defers the way it handles its format specifiers to `T`:

```
template <typename T>
    requires formattable<T>
struct formatter<Optional<T>> {
    formatter<T> underlying;

    constexpr auto parse(auto& ctx) {
        return underlying.parse(ctx);
    }

    auto format(Optional<T> const& v, auto& ctx) const {
        if (v) {
            ctx.advance_to(format_to(ctx.out(), "Some("));
            ctx.advance_to(underlying.format(*v, ctx));
            return format_to(ctx.out(), ")");
        } else {
            return format_to(ctx.out(), "None");
        }
    }
}
```

And this is pretty sensible, I think. In Rust terms, we've implemented `Display` in terms of `Display` and `Debug` in terms of `Debug`.

But that's not exactly what we did for ranges. There we are providing `Display` in terms of either `Debug` or `Display`, depending on the choice of specifier you provide. For instance:

```cpp
std::vector<char> v = {'h', 'e', 'l', 'l', 'o'};
fmt::print("{}\n", v);     // ['h', 'e', 'l', 'l', 'o']
fmt::print("{::}\n", v);   // [h, e, l, l, o]
fmt::print("{::d}\n", v);  // [104, 101, 108, 108, 111]
```

The first line is the default choice for ranges, using the debug formatting of the underlying element type (which prints `char` quoted). The second one, because we're providing a _format-specifier_ explicitly (even if it's empty), is using the default formatting of the underlying type (which does not quote `char`). And the last line uses the `d` specifier for each element (printing the `char`s as integers).

If we skip the first colon for simplicity here, how do you implement `formatter` for a range in this model?

Maybe you're thinking what we have is already incorrect: if I want debug formatting, that's `?`, and if I want display formatting, that's... not `?`. So the above isn't right, `{}` and `{::}` would format the same (unquoted `char`), but if I wanted to get quoting I would use `{::?}` as the specifier.

But even so - how do you implement _that_?

The issue becomes that `formattable<R>` for a range requires _either_ `debug_formattable` _or_ `formattable`. Something like... this:

```cpp
template <ranges::input_range R>
    requires formattable<remove_cvref_t<ranges::range_reference_t<R>>>
          or debug_formattable<remove_cvref_t<ranges::range_reference_t<R>>>
struct formatter<R> {
    using T = remove_cvref_t<ranges::range_reference_t<R>>;

    // see below
    maybe_formatter<T> underlying;

    // parse needs to be provided unconditionally - even if T is only
    // debug-formattable, the format-spec for the type might be ?, which is good
    // enough
    constexpr auto parse(auto& ctx) {
        return underlying.parse(ctx);
    }

    auto format(R const& rng, auto& ctx) const {
        auto out = ctx.out();
        *out++ = '[';
        bool first = true;
        for (auto it = ranges::begin(rng); it != ranges::end(rng); ++it) {
            if (not first) {
                *out++ = ',';
                *out++ = ' ';
            }
            ctx.advance_to(out);
            out = underlying.format(*it, ctx)
        }
        *out++ = ']';
        return out;
    }
};
```

This doesn't look so bad actually. I hid the the complexity in `maybe_formatter<T>`:

```cpp
template <typename T>
    requires formattable<T> or debug_formattable<T>
struct maybe_formatter {
    // pretend this is valid syntax
    if (formattable<T>) {
        formatter<T> underlying;
    }
    if (debug_formattable<T>) {
        bool use_debug_formatting = false;
    }

    constexpr auto parse(auto& ctx) {
        auto it = ctx.begin();
        if (it == ctx.end() or *it == '}') {
            // typically, we just return here and are happy. But now, this means
            // we have an empty spec, which is only allowed if T is formattable
            if constexpr (formattable<T>) {
                // NB: we still call underlying.parse, even though we know the
                return underlying.parse(ctx);
            } else {
                throw format_error("T isn't formattable but using empty spec");
            }
        }

        // here we have at least one character. we need to special-case if the
        // entirety of the context is just ?. Presumably in this case we would
        // add a convenience function on the context for this
        if (*it == '?' and (it + 1 == ctx.end() or it[1] == '}')) {
            if constexpr (debug_formattable<T>) {
                use_debug_formatting = true;
                return it + 1;
            } else {
                throw format_error("T isn't debug formattable");
            }
        }

        // Otherwise, we don't care what the spec is - we just have to parse it
        // If we can
        if constexpr (formattable<T>) {
            return underlying.parse(ctx);
        } else {
            throw format_error("T isn't formattable");
        }
    }

    auto format(T const& value, auto& ctx) const {
        // at this point, we know we had a valid format-spec
    }
};
```

But that isn't really what I want, since formatting `Optional<char>('\t')` with `{}` should give you `Some(\t)` and not `Some(    )`. But formatting with `{:d}` should give you `Some(9)`.

So really it's more like... this?

```cpp
template <typename T>
    requires (formattable<T> or debug_formattable<T>)
struct formatter<Optional<T>> {
    // pretend this is a way to do conditional members
    if (formattable<T>) {
        formatter<T> underlying;
        bool called_parse = false;
    }

    constexpr auto parse(auto& ctx) {
        if constexpr (formattable<T>) {
            called_parse = true;
            return underlying.parse(ctx);
        } else {
            throw format_error("type isn't formattable but parse was invoked");
        }
    }

    auto format(Optional<T> const& v, auto& ctx) const {
        if (v) {
            ctx.advance_to(format_to(ctx.out(), "Some("));
            if constexpr (formattable<T>) {
                if constexpr (debug_formattable<T>) {
                    if (called_parse) {
                        ctx.advance_to(underlying.format(*v, ctx));
                    } else {
                        ctx.advance_to(debug_formattable<T>::format(*v, ctx));
                    }
                } else {
                    ctx.advance_to(underlying.format(*v, ctx));
                }
            } else {
                ctx.advance_to(debug_formattable<T>::format(*v, ctx));
            }
            return format_to(ctx.out(), ")");
        } else {
            return format_to(ctx.out(), "None");
        }
    }
}
```

This seems like a mighty complex implementation, the logic here is:

* if `T` is `debug_formattable`, but not `formattable`, then we ensure that `parse()` isn't called (i.e. we only support `{}`) and formatting goes through `debug_formattable`
* if `T` is `debug_formattable` and `formattable`, then we either use `formatter` or `debug_formatter` depending on whether `parse()` was called
* if `T` is `formattable` but not `debug_formattable`, we just unconditionally use `formatter`

The _outcome_ of this logic is good, but the actual structure here certainly suggests that this design is wrong.

---
