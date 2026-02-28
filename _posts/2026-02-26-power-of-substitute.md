---
layout: post
title: "Behold the power of <code class=\"language-cpp\">meta::substitute</code>"
category: c++
tags:
 - c++
 - c++26
 - reflection
pubdraft: yes
---

> My CppCon 2025 talk, [Practical Reflection](https://youtu.be/ZX_z6wzEOG0), is now online. Check it out!
{:.prompt-info}

Over winter break, I started working on proposal for [string interpolation](https://wg21.link/p3951). It was a lot of fun to work through implementing, basically an hour a day during my daughter's nap time. The design itself is motivated by wanting to have a lot more functionality other than just formatting — and one of the examples in the paper was implementing an algorithm that does highlighting of the interpolations, such that:

```cpp
highlight_print(fmt::emphasis::bold
                | bg(fmt::color::blue)
                | fg(fmt::color::white),
                t"x={x} and y={y:*^{width}} and z={z}!\n");
```

would print this:

> x=<b><span style="background-color:blue;color:white">5</span></b> and y=<b><span style="background-color:blue;color:white">\*10\*</span></b> and z=<b><span style="background-color:blue;color:white">hello</span></b>!

without doing any additional parsing work. I got the example from Vittorio Romeo's [original paper](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2019/p1819r0.html#automated-coloring).

Now, when I wrote the paper, I considered this to be a simple example demonstrating something that was possible with the design I was proposing that was _not_ possible with the [other design](https://wg21.link/p3412). I thought that because obviously you need the format string as a compile-time constant in order to parse it at compile time to get the information that you need.

It turns out, that is _not_ the case. And, much to my surprise, I can get the same thing working using this syntax:

```cpp
highlight_print(fmt::emphasis::bold
                | bg(fmt::color::blue)
                | fg(fmt::color::white),
                "x={} and y={:*^{}} and z={}!\n",
                x,
                y,
                width,
                z);
```

The rest of this post will demonstrate how exactly this is possible, thanks to Reflection.

> To be clear, what I mean by "working" and "possible" is that the parsing of the format string — including determining the separation between the string pieces and the replacement fields — happens entirely at compile time. Obviously doing this at runtime is possible.
{:.prompt-info}

## `consteval` Constructors

C++ doesn't have `constexpr` function parameters. While it's always been possible to encode values into types, and C++26 includes a more convenient mechanism of doing so with `std::constant_wrapper<V>` — including the variable template `std::cw<V>` — doing so requires explicitly taking steps at the call site. If you want to consume an argument as a constant, it has to be passed to your function as a constant. And if it's not, then the constant-ness of the argument is lost.

With one exception: the `consteval` constructor.

The way that type-checking works in `fmt::format` and `std::format` is that when you write something like `std::format("x={}", 42)`, the first parameter of the relevant specialization of `std::format` has type `std::format_string<int>` — and looks something like this:

```cpp
template <>
struct format_string<int> {
    string_view str;

    template <class S>
        requires std::convertible_to<S, std::string_view>
    consteval format_string(S s)
        : str(s)
    {
        // ...
    }
};
```

The rule for a `consteval` constructor is that the call has to be constant, and the language ensures that — in this case that `std::format_string<int>("x={}")` is a constant expression. Evaluated at compile time. The body of the constructor ensures the format string is valid, and otherwise just stores its input.

Once control flow enters the body of `std::format<int>(fmt, arg)`, we know we have type-checked the format string, and we can use `fmt.str` to actually go ahead and do the formatting.

That's pretty cool. But we can go deeper.

## The End Goal

Let's skip ahead a bit and go straight to the end goal. The design I'm proposing for string interpolation is that the result of a t-string is an object with a member for each captured expression, plus a bunch of `static consteval` functions to retrieve everything interesting about the original string.

That allows implementing highlighting by simply looping over the relevant pieces, with lots of dots, taking advantage of a number of new C++26 features (from top to bottom: packs in structured bindings, expansion statements, `views::indices`, adding tuple support to `std::index_sequence`, and pack indexing):

```cpp
template <TemplateString S>
auto highlight_print(fmt::text_style style, S&& s) -> void {
    constexpr size_t N = s.num_interpolations();

    auto& [...exprs] = s;

    template for (constexpr int I : std::views::indices(N)) {
        fmt::print(s.string(I));

        constexpr auto interp = s.interpolation(I);
        constexpr auto [...J] = std::make_index_sequence<interp.count>();
        fmt::print(style,
                   interp.fmt,
                   exprs...[interp.index + J]...);
    }

    fmt::print(s.string(N));
}
```

I think this is actually pretty nice. But this requires a specific shape for the t-string object, and that shape isn't something that I can actually generate in library code. And the premise here is that we are still getting the arguments as a parameter pack, rather than a single object.

Instead, we can split out the interpolation information like so:

```cpp
struct Interpolation {
    char const* fmt;
    int index;
    int count;
};

struct Information {
    size_t num_interpolations;
    char const* const* strings;
    Interpolation const* interpolations;
};
```

Which allows me to pass this as a constant template parameter, with only basically aesthetic changes in the implementation (highlighted). I renamed it to `highlight_print_impl` for reasons that will become clear later:

```cpp
template <Information Info, class... Args>
auto highlight_print_impl(fmt::text_style style, Args&&... exprs) -> void {
    constexpr size_t N = Info.num_interpolations;

    template for (constexpr int I : std::views::indices(N)) {
        fmt::print(Info.strings[I]);

        constexpr auto interp = Info.interpolations[I];
        constexpr auto [...J] = std::make_index_sequence<interp.count>();
        fmt::print(style,
                   interp.fmt,
                   exprs...[interp.index + J]...);
    }

    fmt::print(Info.strings[N]);
}
```
{: data-line="3,8,15" .line-numbers  }

That's where we want to end up. How do we get there?

## Functions, not Function Templates

In order to get a constant template parameter of type `Information`, we need to produce the value at compile time. That's a `consteval` function. And in order to be able to parse the format string properly, we need the types — which we have.

It's tempting to start like this:

```cpp
template <class... Ts>
consteval auto parse_information(std::string_view sv)
    -> Information;
```

And that wouldn't necessarily be _wrong_. This is a very familiar entry-point, and is definitely what you would've written in prior standards. But with Reflection, we don't necessarily actually need to write function templates anymore. We want to write _functions_.

Let's instead start here:

```cpp
consteval auto parse_information(std::span<std::meta::info const> arg_types,
                                 std::string_view sv)
    -> Information;
```

Thankfully, we don't really have to manually implement all the formatting — `{fmt}` provides just about everything we need (although in a `detail` namespace). `{fmt}` provides a special version of `parse_context` that's used for compile-time parsing, which is `fmt::detail::compile_parse_context`.

If we were writing a function template, we'd start this way:

```cpp
template <class... Ts>
consteval auto parse_information(std::string_view sv)
    -> Information
{
    fmt::detail::type types[] = {
        fmt::detail::mapped_type_constant<Ts, char>::value...
    };
    auto ctx = fmt::detail::compile_parse_context<char>(
        sv, sizeof...(Ts), types);

    // ..
}
```

How do we produce the `fmt::detail::type[]` array that we need for the `fmt::detail::compile_parse_context` constructor if we don't have a parameter pack of types? We just have a `span<meta::info const>`?

That's what `std::meta::substitute` is for.

We cannot splice `types[0]` to get the type that it represents — because in order to splice, you need a constant expression, and function parameters are not constant. However, let's say we had a suitably-shaped template lying around. In this case, we want a variable template:

```cpp
template <class... Ts>
constexpr fmt::detail::type fmt_types[] = {
    fmt::detail::mapped_type_constant<Ts, char>::value...
};
```

What we actually want is the specialization `fmt_types<Ts...>` for each of the types represented by the reflections in `types`. We cannot get that directly. However, we can get it indirectly as follows:

```cpp
consteval auto make_parse_context(std::span<std::meta::info const> arg_types,
                                  std::string_view sv)
    -> fmt::detail::compile_parse_context<char>
{
    auto r = substitute(^^fmt_types, arg_types);
    // now what??
}
```
{: data-line="5" .line-numbers }

What `std::meta::substitute` does is takes a reflection representing any template (like `fmt_types`) and a sequence of reflections (like `arg_types`), performs the substitution internally and returns a reflection representing that result. We wanted `fmt_types<Ts...>`, the array — but instead we ended up with `^^fmt_types<Ts...>`, a value of type `std::meta::info`.

We _still_ cannot splice `r`, because `r` still isn't a constant. But we have information about it. We specifically know that it represents a variable whose type is `fmt::detail::type const[N]` (where `N` is `arg_types.size()`, actually). As such, we can use another reflection function — `std::meta::extract` — to pull out the value.

> `std::meta::extract<T>` is roughly analogous to `std::any_cast<T>` for `std::any`: if you know what your reflection represents, you can pull that value out. If you get it wrong, it will fail.
{:.prompt-info}

In particular, you can extract an array of `T[N]` as a `T*`, which is precisely what we need here:

```cpp
template <class... Ts>
constexpr fmt::detail::type fmt_types[] = {
    fmt::detail::mapped_type_constant<Ts, char>::value...
};

consteval auto make_parse_context(std::span<std::meta::info const> arg_types,
                                  std::string_view sv)
    -> fmt::detail::compile_parse_context<char>
{
    auto r = substitute(^^fmt_types, arg_types);
    return fmt::detail::compile_parse_context<char>(
        sv,
        arg_types.size(),
        extract<fmt::detail::type const*>(r)
    );
}
```
{: data-line="14" .line-numbers }


And now we have our `parse_context`, without a template:

```cpp
consteval auto parse_information(std::span<std::meta::info const> arg_types,
                                 std::string_view sv)
    -> Information
{
    auto ctx = make_parse_context(arg_types, sv);

    // ...
}
```
{: .line-numbers }

## Promoting to Static Storage

In order to build up the `Information` object we need to end up with, we need to build up a list of `strings` and a list of `interpolations`.

However, we need to be careful — the resulting `Information` needs to be usable as a constant template parameter. Which means all of its constituent pointers need to point to something with static storage duration. How could we possibly do _that_?

That is, once we start actually parsing, what... do we do here:

```cpp
consteval auto parse_information(std::span<std::meta::info const> arg_types,
                                 std::string_view sv)
    -> Information
{
    auto ctx = make_parse_context(arg_types, sv);

    std::vector<char const*> strings;
    std::vector<Interpolation> interpolations;

    while (true) {
        // next string (not handling escaped braces for now)
        auto next = std::find(ctx.begin(), ctx.end(), '{');
        auto next_string = std::string_view(ctx.begin(), next);
        strings.push_back(/* ???? */);
        if (next == ctx.end()) {
            break;
        }

        // next interpolation
        // ...
    }

    // ...
}
```
{: data-line="14" .line-numbers }

Now for this particular problem, our input — `sv` — is actually a string literal. So we could simply come up with a way to return pieces of it. Instead, I'm going to take the opportunity to introduce an interesting family of reflection functions:

* `std::define_static_string(s)` takes a string and returns a pointer to a static storage, constexpr array (that is null-termintaed)
* `std::define_static_array(r)` takes a range and returns a `span` to a static storage, constexpr array
* `std::define_static_object(o)` takes an object and returns a pointer to a static storage, constexpr object

There is an additional property that these functions have that the returned value is usable as a template argument, and is unique.

So the next string is:

```cpp
strings.push_back(std::define_static_string(next_string));
```

## Parsing an Interpolation

Now that we got to the `{` of a replacement-field, what do we do next?  If this were regular old write-function-templates-to-solves-problems C++, we would of course write a function template. The only way to really correctly parse the specifiers for a given type `T` is to use its formatter, `fmt::formatter<T>`, and call `parse`:

```cpp
template <class T>
constexpr auto parse_next_impl(fmt::parse_context<char>& ctx) -> void {
    auto cur = ctx.begin();
    if (*cur == ':') {
        ++cur;
    }
    ctx.advance_to(cur);

    // we don't actually need this value, but we do need
    // to consume it to make sure we know what we're doing
    (void)ctx.next_arg_id();

    fmt::formatter<T> f;
    cur = f.parse(ctx);
    if (cur != ctx.end()) {
        ++cur;
    }
    ctx.advance_to(cur);
}
```

Recall though — we're writing a function, not a function template. We don't have `T`, we have a value of type `std::meta::info` which represents `T`. But now we wrote ourselves a function template that does the work we need to do. And, as with earlier with `fmt_types`, we know a lot about this function template. In particular, every specialization has type `auto(fmt::parse_context<char>&)->void`.

Once again, we do the `substitute`/`extract` two-step here — except it's a little more involved now:

```cpp
// advance the context to the format specifier
// e.g. given "x={} and y={:*^{}} and z={}!"
// we are here:   ^        ^             ^
ctx.advance_to(next + 1);

// we need the current arg id (to know which type we're on)
int const index = peek_arg_id(ctx);

// this is now a reflection representing the function we need to call
// note that arg_types is just a span, so this is regular indexing
std::meta::info const parse_next_fn_refl =
    substitute(^^parse_next_impl, {arg_types[index]});

// extract the actual function pointer — whose type we know
auto const parse_next_fn =
    extract<auto(*)(fmt::parse_context<char>&)->void>(parse_next_fn_refl);

// and then... just call it
parse_next_fn(ctx);

// which would have advanced the arg id, giving us the count
int const count = peek_arg_id(ctx) - index;

// and now we have all the information we need to construct our
// actual Interpolation object
interpolations.push_back({
    .fmt = define_static_string(std::string_view(next, ctx.begin())),
    .index = index,
    .count = count,
});
```
{: .line-numbers }

This `substitute`/`extract`/invoke dance is remarkably powerful.

## The Rest of the Owl

When we're all done with the `strings` and `interpolations`, we need to actually put together the `Information` object to return, which is just a few `define_static_array` calls away:

```cpp
return Information {
    .num_inteprolations = interpolations.size(),
    .strings = define_static_array(strings).data(),
    .interpolations = define_static_array(interpolations).data(),
};
```

Although, I don't actually want this function to return an `Information`. We don't really need it as a value anyway, we're going to pass it as a template argument in a bit.

Now, one way of thinking about `substitute` is that it removes a layer of reflection from all of its arguments. For instance, `substitute(^^std::vector, {^^int})` removes a layer of reflection from the first argument, giving the class template `std::vector`, and removes a layer of reflection from the second argument, giving the type `int`, and puts them together — adding another layer of reflection back, yielding `^^std::vector<int>`.

In order to pass `Information` as an argument through `substitute` (spoiler alert), we need to add a layer of reflection first. That's `std::meta::reflect_constant`.

The whole function (again, not template) looks like this:

```cpp
consteval auto parse_information(std::span<std::meta::info const> arg_types,
                                 std::string_view sv)
    -> std::meta::info
{
    auto ctx = make_parse_context(arg_types, sv);

    std::vector<char const*> strings;
    std::vector<Interpolation> interpolations;

    while (true) {
        // next string
        auto next = std::find(ctx.begin(), ctx.end(), '{');
        strings.push_back(define_static_string(
            std::string_view(ctx.begin(), next)));
        if (next == ctx.end()) {
            break;
        }

        // next interpolation
        ctx.advance_to(next + 1);
        int const index = peek_arg_id(ctx);
        auto parse_fn = substitute(^^parse_next_impl, {arg_types[index]});
        extract<auto(*)(fmt::parse_context<char>&)->void>(parse_fn)(ctx);
        int const count = peek_arg_id(ctx) - index;

        interpolations.push_back({
            .fmt = define_static_string(
                std::string_view(next, ctx.begin())),
            .index=index,
            .count=count,
        });
    }

    auto info = Information{
        .num_interpolations = interpolations.size(),
        .strings = define_static_array(strings).data(),
        .interpolations = define_static_array(interpolations).data(),
    };

    return std::meta::reflect_constant(info);
}
```
{: .line-numbers }

But... what do we _do_ with this function?

Recall, the only mechanism we have at our disposal to accept _constant_ arguments without having the caller wrap is via a `consteval` constructor. We do something with the same shape that `{fmt}` already does.

This one has to be a template:

```cpp
template <class... Ts>
struct highlight_format_string {
    template <class S>
        requires std::convertible_to<S, std::string_view>
    consteval highlight_format_string(S str) {
        // a reflection representing the Information that we
        // parsed out of str
        std::meta::info interp_info =
            parse_information({remove_cvref(^^Ts)...},
                              std::string_view(str));

        // remember highlight_print_impl? this is the
        // specialization of it that we actually want
        std::meta::info func_refl =
            substitute(^^highlight_print_impl,
                       {interp_info, ^^Ts...});

        // ... whose type we know, so we can extract
        // the function pointer to it, and store that
        // as a member!
        this->impl = extract<
            auto(*)(fmt::text_style, Ts&&...) -> void
            >(func_refl);
    }

    // I usually put my data members at the top of the class
    // but that would ruin the dramatic reveal in this case
    auto (*impl)(fmt::text_style, Ts&&...) -> void;
}
```
{: .line-numbers }

> This has to be a template because it is our only entry point into getting the types (`Ts...`). Otherwise, we'd just get the format string, but wouldn't know how to parse it.
{:.prompt-info}

For `std::format_string`/`fmt::format_string` — the `consteval` constructor simply type checks, and otherwise it stores as a member the argument that it got passed in.

But here, for `highlight_format_string`, we're not storing the string — we're computing the correct function to call with all the information we've already parsed. That function already does everything we need it to do at runtime, we simply need to call it:

```cpp
template <class... Ts>
auto highlight_print(fmt::text_style style,
                     std::type_identity_t<highlight_format_string<Ts...>> fmt,
                     Ts&&... args) -> void {
    fmt.impl(style, (Ts&&)args...);
}
```
{: data-line="5" .line-numbers }


And [we're done](https://compiler-explorer.com/z/zMPnsaqfa). It actually works.

## Conclusion

In short, we're accepting a regular string literal argument — but parsing it completely at compile time and generating a function which can format it based on the shape that we pulled out at compile time. This is all built on top of the power of `std::meta::substitute` (which effectively allows us to take regular values and turn them in constants) and `std::meta::extract` (which allows us to pull values back out of a seemingly opaque store, since we know their shape).

And the main engine of this entire implementation is a function. Not a function template, a regular function.

It is remarkable to me that this is possible. I didn't think it was as little as a couple months ago.

Now, it would be tempting to call this implementation insane — probably because it is. So let's instead talk about if there's anything we could improve in the language to make this a little more direct. For instance, what would Zig do here? It turns out, that Zig has two language features that turn out to have significant benefit — and the more beneficial one probably isn't the one you're thinking.

> At least, I think of these as two distinct features. It's possible Zig programmers think of it as one.
{:.prompt-info}

### 1. `constexpr` function params

We have to do this dance with a non-deduced `highlight_format_string<Ts...>` type that has a `consteval` constructor so that we can use the format string in a constant-evaluated context.

A more direct way to do so would be to simply declare that parameter `constexpr` (Zig calls these `comptime`{:.language-zig} parameters), as in:

```cpp
template <class... Ts>
auto highlight_print(fmt::text_style style,
                     constexpr std::string_view fmt,
                     Ts&&... args) -> void {
    // ...
}
```
{: data-line="3" .line-numbers }

This removes a whole layer of indirection from the solution — not just `highlight_format_string<Ts...>` but also the fact that we have to build up that reflection of a function to begin with. We could have `parse_information` simply return us an `Information` and then inline the implementation:

```cpp
template <class... Ts>
auto highlight_print(fmt::text_style style,
                     constexpr std::string_view fmt,
                     Ts&&... args) -> void {
    constexpr Information Info =
        parse_information({remove_cvref(^^Ts)...}, fmt);

    constexpr size_t N = Info.num_interpolations;
    // ... rest of highlight_print_impl ...
}
```
{: data-line="5-6" .line-numbers }

Quite a bit simpler. But wait, there's more.

### 2. `consteval mutable` variables

Even in the above implementation, we still have one source of indirection: we have a function, `parse_information()`, which gave us an `Information` with all the relevant pieces of the format string.

That's something we cannot inline into `highlight_print`, even with a `constexpr` function parameter, because we want to be printing (a fundamentally runtime operation) while we're parsing (something we want to be doing at compile-time). Zig lets us do both at the same time with `comptime var`{:.language-zig}.

A hypothetical approach to C++ syntax might look something like this:

```cpp
template <class... Ts>
auto highlight_print(fmt::text_style style,
                     constexpr std::string_view fmt,
                     Ts&&... args) -> void {
    constexpr fmt::detail::type fmt_types[] = {
        fmt::detail::mapped_type_constant<Ts, char>::value...
    };
    consteval mutable auto ctx =
        fmt::detail::compile_parse_context<char>(
            fmt,
            sizeof...(Ts),
            fmt_types
        );
    consteval mutable int start = 0;

    template for (consteval mutable int i = 0; i != fmt.size(); ++i) {
        if constexpr (fmt[i] == '{') {
            // write the string we have
            fmt::print("{}", std::string_view(&fmt[start], i - start));

            // parse the next interpolation
            ctx.advance_to(fmt.begin() + i + 1);
            constexpr int index = peek_arg_id(ctx);
            constexpr int end =
                fmt::formatter<Ts...[index]>().parse(ctx)
                - fmt.begin();
            constexpr int count = peek_arg_id(ctx);

            // write the next interpolation
            constexpr auto [...J] = std::make_index_sequence<count>();
            fmt::print(style,
                       fmt.sub(i, end - i),
                       args...[index + J]...);

            // update state
            start = i = end;
        }
    }

    // write the last string
    fmt::print("{}", std::string_view(&fmt[start], fmt.size() - start);
}
```
{: data-line="16,22,25,36" .line-numbers }

The more interesting things are the highlight lines: compile-time mutations. These are variables that exist entirely during constant evaluation time, that I can mutate, yet whose values I can use as constants (as in lines 23 and 27). And this capability allows me to implement this entire algorithm in one go without any indirection.

> Well, assuming I wrote it correctly. I'm assuming there are multiple off-by-one errors here and there in the above implementation. But let's try to ignore those — I can't exactly check this.
{:.prompt-info}

In Zig, this just works. In fact, there's a quite similar example [in its documentation](https://ziglang.org/documentation/master/#Case-Study-print-in-Zig).

Is this something we could eventually do in C++? It's certainly a good question.