---
layout: post
title: "Reflecting JSON into C++ Objects"
category: c++
tags:
 - c++
 - c++26
 - reflection
---

Last week, C++26 was finalized in Sofia, Bulgaria — and C++26 will include all of the reflection papers that we were pushing for:

1. [P2996R13](https://isocpp.org/files/papers/P2996R13.html): Reflection for C++26
1. [P3394R4](https://isocpp.org/files/papers/P3394R4.html): Annotations for Reflection
1. [P3293R3](https://isocpp.org/files/papers/P3293R3.html): Splicing a Base Class Subobject
1. [P3491R3](https://isocpp.org/files/papers/P3491R3.html): `define_static_{string,object,array}`
1. [P1306R5](https://isocpp.org/files/papers/P1306R5.html): Expansion Statements
1. [P3096R12](https://isocpp.org/files/papers/P3096R12.pdf): Function Parameter Reflection in Reflection for C++26
1. [P3560R2](https://isocpp.org/files/papers/P3560R2.html): Error Handling in Reflection

Those are in the order in which they were adopted, not in the order of their impact (otherwise splicing base classes would go last). This is a pretty incredible achievement that couldn't have happened without lots of people's work, but no one person is more responsible for Reflection in C++26 than Dan Katz.

So today I wanted to talk about a very cool example that Dan put together on the flight home from Sofia, while I was unconscious a few seats over: the ability to, at compile time, ingest a JSON file and turn it into a C++ object. That is, given a file `test.json` that looks like this:

```json
{
    "outer": "text",
    "inner": { "field": "yes", "number": 2996 }
}
```

We can write this:

```cpp
constexpr const char data[] = {
    #embed "test.json"
    , 0
};

constexpr auto v = json_to_object<data>;
```

And the result of that code is that now we have an object `v`, whose type is shaped like:

```cpp
struct {
    char const* outer;
    struct {
        char const* field;
        int number;
    } inner;
};
```

and whose values are populated from the JSON file accordingly:

```cpp
static_assert(v.outer == "text"sv);
static_assert(v.inner.number == 2996);
static_assert(v.inner.field == "yes"sv);
```

Which is, [incredibly, majestically cool](https://godbolt.org/z/Kn5b46T8j).

The remainder of this post will be walking through how to make this happen.

> I attempted to rewrite Dan's example using Boost.JSON, since the actual JSON parsing part of this example isn't the interesting part at all. But Boost.JSON doesn't have `constexpr` support. And neither does `nlohmann::json`. So instead, for the purposes of exposition, I'm going to pretend Boost.JSON works — but you can see the real code in the compiler explorer link.
{:.prompt-info}

> Update in Oct 2025: the [DAW json library](https://github.com/beached/daw_json_link) now supports [this too](https://godbolt.org/z/1MPf7WxMd):
> ```cpp
> struct JSONString {
>     std::meta::info Rep;
>     consteval JSONString(const char *Json)
>       : Rep{parse(daw::json::json_value>(Json))}
>     {}
> };
>
> template <JSONString json>
> consteval auto operator""_json() {
>     return [:json.Rep:];
> }
>
> template <JSONString json>
> inline constexpr auto json_to_object = [: json.Rep :];
>
> using namespace std::literals;
>
> constexpr auto x = R"({"A": 1, "B" : { "C" : "h" }})"_json;
> static_assert(x.A == 1);
> static_assert(x.B.C == "h"sv);
> ```
{:.prompt-info}

## Let's Start Simple

Rather than starting from the full example, let's instead start with a very abbreviated form — that will be good enough to demonstrate everything interesting. We're going to parse a version of JSON object in which we just have one key and one value and that one value is an `int`:

```cpp
consteval auto parse(std::string_view key, int value) -> std::meta::info;
```

Given a value like `{"x": 1}`, what are the steps that we need to take? The end result is that we want to produce a type like:

```cpp
struct S {
    int x;
};
```

And then produce the value

```cpp
S{1}
```

Given our simplified signature, we can start out by getting the right data member and initializer:

```cpp
consteval auto parse(std::string_view key, int value)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    auto member = reflect_constant(data_member_spec(^^int, {.name=key}));
    auto init = reflect_constant(value);

    // ...
}
```
> We're wrapping both values in `reflect_constant` — even though `data_member_spec` is already a `meta::info`. This is because shortly we need to unwrap one layer of reflection. I could add the `reflect_constant` later — but when I make the example more complicated, it'll make more sense to keep it here.
{:.prompt-info}

Next, the only real reason to have `data_member_spec`s is to pass them into `define_aggregate`. That one just needs a class type for us to complete. Here, our `parse` isn't a template, and we need a distinct type for each `member` (since `{"x": 1}` and `{"y": 1}` need to lead to different types). The clever solution here (courtesy of Dan) is as follows:

```cpp
template <std::meta::info ...Ms>
struct Outer {
    struct Inner;
    consteval {
        define_aggregate(^^Inner, {Ms...});
    }
};

template <std::meta::info ...Ms>
using Cls = Outer<Ms...>::Inner;

consteval auto parse(std::string_view key, int value)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    auto member = reflect_constant(data_member_spec(^^int, {.name=key}));
    auto init = reflect_constant(value);

    auto type = substitute(^^Cls, {member});
    // ...
}
```
{: data-line="1-10,20" .line-numbers }

The function `substitute(^^Z, {^^Args...})` yields `^^Z<Args...>`. That is, given a reflection of a template and reflections of template arguments, you get back a reflection of the specialization. This is what I meant earlier when I said we're stripping one layer of reflection — we needed `member` to be a reflection representing a value that is a `data_member_spec` so that we could instantiate `Cls` with reflections representing `data_member_spec`s directly.

`type` is now a reflection representing a unique type for each set of non-static data members. Importantly, the type that it represents is automatically deduplicated and has external linkage. I think this might prove to be a common idiom for creating types from inside of algorithms like this.

Now, we have our type (`type`) and our initializers (`init`), so we need to simply put them together. That is another call to `substitute`. As you can start to see, `substitute` is one of the sneakily most useful functions in the entirety of the library API:

```cpp
template <std::meta::info ...Ms>
struct Outer {
    struct Inner;
    consteval {
        define_aggregate(^^Inner, {Ms...});
    }
};

template <std::meta::info ...Ms>
using Cls = Outer<Ms...>::Inner;

template <class T, auto... Vs>
inline constexpr auto construct_from = T{Vs...};

consteval auto parse(std::string_view key, int value)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    auto member = reflect_constant(data_member_spec(^^int, {.name=key}));
    auto init = reflect_constant(value);

    auto type = substitute(^^Cls, {member});
    return substitute(^^construct_from, {type, init});
}
```
{: data-line="12-13,24" .line-numbers }

With that, we have enough to get these assertions to pass:

```cpp
static_assert([: parse("x", 1) :].x == 1);
static_assert([: parse("y", 2) :].y == 2);
```

They may not seem like much, but we're synthesizing two class types with different members to get this to work. That's pretty cool.

## From One to Many

Now that we have one, single key/value pair working, it's not that much of a stretch to generalize this out to arbitrarily many key/value pairs. Both of the templates we're substituting into (`Cls` and `construct_from`) are already variadic, so I won't bother repeating them. We just need to generalize our implementation.

So far we had one `member` and one `init`, both of type `info`. Those both need to become `vector<info>`s:

```cpp
consteval auto parse(std::string_view key, int value)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits;

    members.push_back(reflect_constant(
        data_member_spec(^^int, {.name=key})));
    inits.push_back(reflect_constant(value));

    auto type = substitute(^^Cls, members);
    inits.insert(inits.begin(), type);
    return substitute(^^construct_from, inits);
}
```
{: .line-numbers }

We needed to insert `type` at the front of `inits` because `construct_from` needs to be instantiated first with the type and then all the initializers. But this approach is a little bit awkward, so we can clean it up by first adding a placeholder to `inits` and then just replacing it later:

```cpp
consteval auto parse(std::string_view key, int value)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    members.push_back(reflect_constant(
        data_member_spec(^^int, {.name=key})));
    inits.push_back(reflect_constant(value));

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="7,13" .line-numbers }

We still only have one key-value pair, but we've got the structure we need to tackle multiples.

## Full Metal JSON

As I mentioned earlier, Boost.JSON doesn't work in `constexpr`. But the point of this blog isn't to illustrate how to parse JSON, it's how to turn a JSON object into a C++ struct. So I'm going to just pretend that Boost.JSON works.

Instead of a `string_view` and an `int` we're going to take a `boost::json::object` and iterate over all the key/value pairs. The broad structure of the function still looks the same:

```cpp
consteval auto parse(boost::json::object object)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    for (auto const& [key, value] : object) {
        // ...
    }

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="1,9-11" .line-numbers }

`value` is now a `boost::json::value`, which could be any of the things that a JSON value could be. For simplicity I'm going to pretend that those can only be (1) a number, (2) a string, or (3) an object. We'll do those in order.

> Now, JSON numbers are actually pretty complex — because which arithmetic type do you want? `i64`? `u64`? `double`? Again, not the point of this blog, so I'm just going to pick `int`.
{:.prompt-info}

The number case should look familiar, since we did that in a previous section — the only difference is where the number comes from:

```cpp
consteval auto parse(boost::json::object object)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    for (auto const& [key, value] : object) {
        if (value.is_number()) {
            members.push_back(reflect_constant(
                data_member_spec(^^int, {.name=key})));
            inits.push_back(reflect_constant(
                value.to_number<int>()));
        } else {
            // ...
        }
    }

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="10-14" .line-numbers }

Since the member part is going to be the same in all cases — we're adding some data member whose name is `key` — I'll preemptively refactor that:

```cpp
consteval auto parse(boost::json::object object)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    for (auto const& [key, value] : object) {
        auto add_member = [&](std::meta::info type){
            members.push_back(reflect_constant(
                data_member_spec(type, {.name=key})));
        };

        if (value.is_number()) {
            add_member(^^int);
            inits.push_back(reflect_constant(
                value.to_number<int>()));
        } else {
            // ...
        }
    }

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="10-13,16" .line-numbers }

Next, strings. Strings actually pose an interesting problem because we need to be able to pass the initializer as a constant template argument. Those cannot be string literals. Additionally, when we start creating nested objects, we need those inner objects to be usable as constant template arguments too. That means we can't use `string_view` — it's not a structural type yet.

> Sorry, [I tried](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2024/p3380r1.html).
{:.prompt-info}

So we're going to stick with `char const*`. Thankfully, we have precisely a function that we can use to take a string value and get a reflection of a null-terminated, static storage duration constexpr array of `char` with those contents: `std::meta::reflect_constant_string`:

```cpp
consteval auto parse(boost::json::object object)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    for (auto const& [key, value] : object) {
        auto add_member = [&](std::meta::info type){
            members.push_back(reflect_constant(
                data_member_spec(type, {.name=key})));
        };

        if (value.is_number()) {
            add_member(^^int);
            inits.push_back(reflect_constant(
                value.to_number<int>()));
        } else if (auto s = value.if_string()) {
            add_member(^^char const*);
            inits.push_back(std::meta::reflect_constant_string(*s));
        } else {
            // ...
        }
    }

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="19-21" .line-numbers }

Lastly, we have the object case. Given an arbitrary JSON object, how do we get a reflection to a C++ value of that object? Well, we've already written that function. That's `parse`! Recursion is cool like that. In this case, we don't immediately have the type of the object we need to produce — but once we get the reflection of the value, we can get the type after the fact:

```cpp
consteval auto parse(boost::json::object object)
    -> std::meta::info
{
    using std::meta::reflect_constant;

    std::vector<std::meta::info> members;
    std::vector<std::meta::info> inits = {^^void};

    for (auto const& [key, value] : object) {
        auto add_member = [&](std::meta::info type){
            members.push_back(reflect_constant(
                data_member_spec(type, {.name=key})));
        };

        if (value.is_number()) {
            add_member(^^int);
            inits.push_back(reflect_constant(
                value.to_number<int>()));
        } else if (auto s = value.if_string()) {
            add_member(^^char const*);
            inits.push_back(std::meta::reflect_constant_string(*s));
        } else {
            std::meta::info inner = parse(value.as_object());
            add_member(remove_const(type_of(inner)));
            inits.push_back(inner);
        }
    }

    inits[0] = substitute(^^Cls, members);
    return substitute(^^construct_from, inits);
}
```
{: data-line="23-25" .line-numbers }

And that's *it*. Or at least, that would be it if we could use Boost.JSON.

## Wrapping It Up

In Dan's [actual implementation](https://godbolt.org/z/Kn5b46T8j) (with some edits), `parse_json` took a `string_view` and actually had to, well, parse all the JSON:

```cpp
consteval auto parse_json(std::string_view json) -> std::meta::info {
    // stuff
}
```

It followed the same structure I presented here though. There's one last thing we have to do: provide a slightly nicer façade:

```cpp
struct JSONString {
    std::meta::info Rep;
    consteval JSONString(const char *Json) : Rep{parse_json(Json)} {}
};

template <JSONString json>
consteval auto operator""_json() {
    return [:json.Rep:];
}

template <JSONString json>
inline constexpr auto json_to_object = [: json.Rep :];
```

And that's that. We can pull in an arbitrary JSON file using the new `#embed` and immediately turn that into a C++ object:

```cpp
constexpr const char data[] = {
    #embed "test.json"
    , 0
};

constexpr auto v = json_to_object<data>;
```

Or we an even operate directly on string literals using the UDL:

```cpp
static_assert(
    R"({"field": "yes", "number": 2996})"_json
    .number == 2996);
```

We've basically implemented an [F# JSON type providers](https://fsprojects.github.io/FSharp.Data/library/JsonProvider.html) as a fairly short library. Granted, it's not precisely the same interface — but the F# design is really only a slight refactor on top of what's presented here.

Reflection is a whole new language.