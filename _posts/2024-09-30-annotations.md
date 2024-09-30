---
layout: post
title: "Code Generation in Rust vs C++26"
category: c++
tags:
 - c++
 - c++26
 - reflection
---

One of the things I like to do is compare how different languages solve the same problem — especially when they end up having very different approaches. It's always educational. In this case, a bunch of us have been working hard on trying to get reflection — a really transformative language feature — into C++26. Fundamentally, reflection itself can be divided into two pieces:

1. Introspection — the ability to ask questions about your program during compilation
2. Code Generation — the ability to have your code write new code

[P2996](https://wg21.link/p2996) (Reflection for C++26) is the (huge) core proposal that fundamentally deals with the first problem, along with setting the foundation for being able to extend this feature in lots of different directions in the future, including generation (for which our design is [P3294](https://wg21.link/p3294)). But introspection, while valuable, is only half of the piece. Andrei Alexandrescu went so far as to claim in his CppCon talk that introspection without generation is useless.

> Or at least he did in the early slides he sent me and I told him to tone it down a notch, so perhaps in the actual talk (whose video I have not seen yet), he just called it... Mostly Useless.
{:.prompt-info}

Now, C++ does have one code generation facility today: C macros. It's just a very poor and primitive one. Poor because of their complete lack of hygiene to the point where you could be accidentally invoking macros without knowing it (and standard library implementations guard against that), and primitive because even remarkably simple things conceptually (like iteration or conditions) require true wizardry to implement. That said, there are still plenty of problems today for which C macros are the best solution — which really says something about the need for proper code generation facilities.

On the other hand, if we look at Rust — Rust does not actually have any introspection facilities *at all*, but it does have a mature code generation facility in the form of its declarative and procedural macros. Today, this post is just going to look at procedural macros — specifically the derive macro. We're going to look at two problems solved by using the derive macro, how those actually work, and how we are proposing to solve the same problems in a very different way for C++26.

> Now, I'm not a Rust programmer, so I apologize in advance for getting things wrong here. Please let me know if I make any egregious mistakes.
{:.prompt-warning}

## Pretty-Printing a Struct

Once you learn how to declare a type with some new members, one of the first things you're going to want to do is to make your type debug-printable. Not only because in general that's a very useful operation, but also because it's _extremely_ easy to do:

```rust
#[derive(Debug)]
struct Point {
    x: i32,
    y: i32,
}

fn main() {
    let p = Point { x: 1, y: 2 };
    // prints: p=Point { x: 1, y: 2 }
    println!("p={p:?}");
}
```

That first line of code makes `Point` debug-printable — which means it prints the type name and then all the member names and values, in order.

> In my copy of the Rust Programming Language book, you're shown how to declare a `struct` on page 82 and how to make it debug-printable on page 89. It's basically one of the first things you're shown how to do.
>
> Also for this specific task, Rust has `dbg!(p)`{:.lang-rust}, but I'm using `println!`{:.lang-rust} just to be closer to the eventual C++ solution.
{:.prompt-info}

And since this is a programmatic annotation, if I go back later and add a new field to `Point` (let's say I decide that I wanted this to be 3-dimensional and I need a `z`), the debug-printing will be automatically updated to print the new field.

All of which is to say: Pretty easy!

The question you might ask is — how, *specifically*, does this work? What is the interaction between the `derive` macro and the `Debug` trait that causes this to work?

As I mentioned earlier, unlike what we're proposing for C++26, Rust doesn't have any kind of _introspection_. There is no mechanism in the language to ask for the members of `Point` and iterate over them.

Instead, the `derive` macro does something very different: it is a function that takes a token stream of the struct that it annotates and its job is to return a token stream of code to inject after the input. That injected code doesn't actually need to be remotely related to the input (the [Rust docs](https://doc.rust-lang.org/reference/procedural-macros.html#derive-macros) have an example which just completely ignores the input and instead injects a function which returns `42`).

In this case, we sidestep the lack of introspection by actually getting the token sequence input of `Point`, _parsing it_, and using that parsed result to produce the output we need. I suppose this is still a kind of introspect — just one that can only be explicitly opted into in narrow circumstances.

Specifically, the `derive` macro for this example will emit the following (which I got from `cargo expand`):

```rust
#[automatically_derived]
impl ::core::fmt::Debug for Point {
    #[inline]
    fn fmt(&self, f: &mut ::core::fmt::Formatter) -> ::core::fmt::Result {
        ::core::fmt::Formatter::debug_struct_field2_finish(
            f,
            "Point",
            "x",
            &self.x,
            "y",
            &&self.y,
        )
    }
}
```

It's not especially complicated code, but the point is that Rust programmers don't have to deal with writing this boilerplate. They just have to learn how to write one line (or really, not even one full line) of code: `#[derive(Debug)]`{:.lang-rust}. That's the power of code generation.

Nevertheless, even here the result is quite informative. Why is it `&self.x` but `&&self.y`, with the extra reference? Here, Rust's inability to do introspection comes into place. In Rust, your last field can be an unsized type. An unsized type can be printed, [but needs an extra indirection](https://github.com/rust-lang/rust/blob/74fd001cdae0321144a20133f2216ea8a97da476/compiler/rustc_builtin_macros/src/deriving/debug.rs#L101-L102). The derive macro has no way of knowing whether `y` is sized or not (in this case it's an `i32`, which is `Sized`), so in an effort to support both cases, it just preemptively adds the extra indirection.


In C++, with what we're proposing, if I try to be as familiar to the Rust syntax as possible, I can make it work [like this](https://godbolt.org/z/bcYE7nY4s):

```cpp
struct [[=derive<Debug>]] Point {
    int x;
    int y;
};

int main() {
    auto p = Point{.x=1, .y=2};
    // prints p=Point{.x=1, .y=2}
    std::println("p={}", p);
}
```

Now, fundamentally, there are some similarities between how C++ and Rust do formatting (which I've [touched on before]({% post_url 2023-01-02-rust-cpp-format %})). In Rust, you have to provide an `impl` for the `Debug` trait. In C++, you have to specialize `std::formatter` (we don't differentiate between `Debug` and `Display`). As I showed earlier, the Rust `#[derive(Debug)]`{:.lang-rust} macro invocation injects the correct `impl` of `Debug` for the type. But in C++, we're... not actually doing that at all.

The specific language feature I'm making use of here is called an *annotation*. It will be proposed in [P3394](https://wg21.link/p3394) (link will work when it's published in October 2024) and was first revealed by Daveed Vandevoorde at his [CppCon closing keynote](https://www.youtube.com/watch?v=wpjiowJW2ks). The goal of the proposal is to let you annotate declarations in a way that introspection can observe. Notably, no injection is happening. We're just extending introspection a bit.

However, given that C++ _does_ have introspection (or will, with P2996), that's sufficient to get the job done. We can, up front, provide a specialization of `std::formatter` that is enabled if the type is annotated with `derive<Debug>`, which it itself just an empty value:

```cpp
template <auto V> struct Derive { };
template <auto V> inline constexpr Derive<V> derive;

inline constexpr struct{} Debug;

template <class T> requires (has_annotation(^^T, derive<Debug>))
struct std::formatter<T> {
    // ...
};
```

And once we have that, the body of the specialization can introspect on `T` to get all the information that we need to display: we can iterate over all the non-static data members, formatting their name and value. A simplified implementation would be (the link above has a more complicated implementation):

```cpp
template <class T> requires (has_annotation(^^T, derive<Debug>))
struct std::formatter<T> {
    constexpr auto parse(auto& ctx) { return ctx.begin(); }

    auto format(T const& m, auto& ctx) const {
        auto out = std::format_to(ctx.out(),
                                  "{}", display_string_of(^^T));
        *out++ = '{';

        bool first = true;
        [:expand(nonstatic_data_members_of(^^T)):] >> [&]<auto nsdm>{
            if (not first) {
                *out++ = ',';
                *out++ = ' ';
            }
            first = false;

            out = std::format_to(out,
                                 ".{}={}",
                                 identifier_of(nsdm), m.[:nsdm:]);
        };

        *out++ = '}';
        return out;
    }
};
```
{: .line-numbers }

In a way, we're still generating code — templates are essentially a form of code generation in C++. But it's interesting that here we're achieving the same end with a very different mechanism.

Note also that this is the _complete_ implementation. It is not a lot of code.

## JSON Serialization

Building on the debug-printing example, where we just wanted to print all the members in order. What if we wanted to do something slightly more involved? When dealing with serialization, it's quite common to want the serialized format to not be _exactly_ the same as the names of all of your members. Sometimes the desired names for your fields have to be different. Sometimes, the desired format is even impossible to replicate in the language — the field name you want to serialize into might happen to be a language keyword, or have a space in it, or so forth.

This is why the [serde](https://serde.rs/) library provides a lot of attributes you can add to types and members to control the logic. Taking a simple example:

```rust
use serde::Serialize;
use serde_json;

#[derive(Serialize)]
struct Person {
    #[serde(rename = "first name")]
    first: String,

    #[serde(rename = "last name")]
    last: String,
}

fn main() {
    let person = Person {
        first: "Peter".to_owned(),
        last: "Dimov".to_owned(),
    };
    let j = serde_json::to_string(&person).unwrap();

    // prints {"first name":"Peter","last name":"Dimov"}
    println!("{}", j);
}
```

As with `Debug`, the derive macro for `Serialize` will inject an implementation for us, which, in this case, looks like this:

```rust
#[doc(hidden)]
#[allow(non_upper_case_globals, unused_attributes, unused_qualifications)]
const _: () = {
    #[allow(unused_extern_crates, clippy::useless_attribute)]
    extern crate serde as _serde;
    #[automatically_derived]
    impl _serde::Serialize for Person {
        fn serialize<__S>(
            &self,
            __serializer: __S,
        ) -> _serde::__private::Result<__S::Ok, __S::Error>
        where
            __S: _serde::Serializer,
        {
            let mut __serde_state = _serde::Serializer::serialize_struct(
                __serializer,
                "Person",
                false as usize + 1 + 1,
            )?;
            _serde::ser::SerializeStruct::serialize_field(
                &mut __serde_state,
                "first name",
                &self.first,
            )?;
            _serde::ser::SerializeStruct::serialize_field(
                &mut __serde_state,
                "last name",
                &self.last,
            )?;
            _serde::ser::SerializeStruct::end(__serde_state)
        }
    }
};
```

Here you can see the desired field names (`"first name"` and `"last name"`) coupled with their actual members. The funny construct `false as usize + 1 + 1`{:.lang-rust} is the number of fields to be serialized (which in this case is obviously `2`). This spelling in particular  is a consequence of wanting to support a different attribute.

For example, if we added a middle name that we wanted to serialize only if it wasn't empty, there's an attribute for that:

```rust
#[derive(Serialize)]
struct Person {
    #[serde(rename = "first name")]
    first: String,

    #[serde(rename = "middle name", skip_serializing_if = "String::is_empty")]
    middle: String,

    #[serde(rename = "last name")]
    last: String,
}
```

Which generates the following code (with the new additions highlighted):

```rust
#[doc(hidden)]
#[allow(non_upper_case_globals, unused_attributes, unused_qualifications)]
const _: () = {
    #[allow(unused_extern_crates, clippy::useless_attribute)]
    extern crate serde as _serde;
    #[automatically_derived]
    impl _serde::Serialize for Person {
        fn serialize<__S>(
            &self,
            __serializer: __S,
        ) -> _serde::__private::Result<__S::Ok, __S::Error>
        where
            __S: _serde::Serializer,
        {
            let mut __serde_state = _serde::Serializer::serialize_struct(
                __serializer,
                "Person",
                false as usize + 1 + if String::is_empty(&self.middle) { 0 } else { 1 }
                    + 1,
            )?;
            _serde::ser::SerializeStruct::serialize_field(
                &mut __serde_state,
                "first name",
                &self.first,
            )?;
            if !String::is_empty(&self.middle) {
                _serde::ser::SerializeStruct::serialize_field(
                    &mut __serde_state,
                    "middle name",
                    &self.middle,
                )?;
            } else {
                _serde::ser::SerializeStruct::skip_field(
                    &mut __serde_state,
                    "middle name",
                )?;
            }
            _serde::ser::SerializeStruct::serialize_field(
                &mut __serde_state,
                "last name",
                &self.last,
            )?;
            _serde::ser::SerializeStruct::end(__serde_state)
        }
    }
};
```
{: data-line="18-19,26-37"  }

What would this look like in our annotations model? In C++, we don't really have something like `serde` — where serialization splits up the pieces being serialized and what they are serialized into. At least, I'm not personally aware of such a library. Instead, we just have JSON libraries that handle JSON serialization, TOML libraries that handle TOML serialization, etc. Maybe that's a consequence of missing the language support necessary to make it easy to do this kind of opt in? On the other hand, we _do_ have this model for hashing — that's [Types Don't Know #](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2014/n3980.html).

In any event, while Rust's and C++'s formatting approaches are similar, so the resulting implementations look similar — this isn't true here. So instead of crafting a serde-like library in C++, I'm simply going to show what this might look like for serializing into Boost.JSON.

We'll start with just support for `derive<Serialize>` and `rename`. That's all we need to get [this code to work](https://godbolt.org/z/WYecTKPvY):

```cpp
struct [[=derive<serde::Serialize>]] Point {
    int x, y;
};

struct [[=derive<serde::Serialize>]] Person {
    [[=serde::rename("first name")]] std::string first;
    [[=serde::rename("last name")]] std::string last;
};

int main() {
    // prints {"x":1,"y":2}
    std::cout << boost::json::value_from(Point{.x=1, .y=2}) << '\n';
    // prints {"first name":"Peter","last name":"Dimov"}
    std::cout << boost::json::value_from(Person{.first="Peter", .last="Dimov"}) << '\n';
}
```

And this whole thing is... 21 lines of code, if I keep the same `derive` variable template from before:

```cpp
namespace serde {
    inline constexpr struct{} Serialize{};
    struct rename { char const* field; };
}

namespace boost::json {
    template <class T>
        requires (has_annotation(^^T, derive<serde::Serialize>))
    void tag_invoke(value_from_tag const&, value& v, T const& t) {
        auto& obj = v.emplace_object();
        [:expand(nonstatic_data_members_of(^^T)):] >> [&]<auto M>{
            constexpr auto field = annotation_of<serde::rename>(M)
                .transform([](serde::rename r){
                    return std::string_view(r.field);
                })
                .value_or(identifier_of(M));

            obj[field] = boost::json::value_from(t.[:M:]);
        };
    }
}
```
{: .line-numbers }

This should look familiar after the formatting implementation — since we're basically also doing formatting. It's just that instead of printing a bunch of `name=value` pairs, we're adding them to a JSON object. And then instead of automatically using the identifier of the non-static data member in question, we first try to see if there's a `rename` annotation. `annotation_of<T>()` gives us an `optional<T>`, so we either get the `rename` (and its underlying string) or just fallback to `identifier_of(M)`.

Adding support for `skip_serializing_if` isn't that much more work, and I think helps really illustrate the difference between the C++ and Rust approaches. In Rust, you provide a string — that is injected to be invoked internally. In C++, we'd just provide a callable.

> This is because Rust's attribute grammar can't support a callable here.
{:.prompt-info}

That requires adding a new annotation type:

```cpp
namespace serde {
      inline constexpr struct{} Serialize{};
      struct rename { char const* field; };
      template <class F> struct skip_serializing_if { F pred; };
  }
```

And then the mildly annoying part is parsing it. We need to pull out an annotation that is some specialization of `serde::skip_serializing_if`. If we find one, then we try to invoke its `pred` member — skipping serializing the value if it evaluates to `true`.

The search looks like this (note that we need `skip_if` to be `constexpr` because we need to splice it to invoke it). I'm sure this part can be cleaned up a little with a nicer library API (at the very least an `is_specialization_of`?):

```cpp
constexpr auto skip_if = []() -> std::meta::info {
    auto res = std::meta::info();
    for (auto A : annotations_of(M)) {
        auto type = type_of(A);
        if (has_template_arguments(type)
            and template_of(type) == ^^serde::skip_serializing_if) {
            // found a specialization
            // but check to make sure we haven't found two
            // different ones.
            if (res != std::meta::info() and res != value_of(A)) {
                throw "unexpected duplicate";
            }

            res = value_of(A);
        }
    }

    return res;
}();
```

And then, if we _have_ such an annotation, we then invoke it to see if we need to skip this member. This needs to be an `if constexpr` because if `skip_if` is the null reflection, we can't splice it. Other than that, this logic is exactly what we have to do: if we have such a `skip_serializing_if` annotation, invoke it and, if it's false, skip this member:

```cpp
if constexpr (skip_if != std::meta::info()) {
    if (std::invoke([:skip_if:].pred, t.[:M:])) {
        return;
    }
}
```

You can see the full solution in action [here](https://godbolt.org/z/hvqra8M7K). It has now ballooned to... all of 51 lines of code (with the new logic to support `skip_serializing_if` highlighted):

```cpp
template <auto V> struct Derive { };
template <auto V> inline constexpr Derive<V> derive;

namespace serde {
    inline constexpr struct{} Serialize{};
    struct rename { char const* field; };
    template <class F> struct skip_serializing_if { F pred; };
}

namespace boost::json {
    template <class T>
        requires (has_annotation(^^T, derive<serde::Serialize>))
    void tag_invoke(value_from_tag const&, value& v, T const& t) {
        auto& obj = v.emplace_object();
        [:expand(nonstatic_data_members_of(^^T)):] >> [&]<auto M>{
            constexpr auto field = annotation_of<serde::rename>(M)
                .transform([](serde::rename r){
                    return std::string_view(r.field);
                })
                .value_or(identifier_of(M));

            constexpr auto skip_if = []() -> std::meta::info {
                auto res = std::meta::info();
                for (auto A : annotations_of(M)) {
                    auto type = type_of(A);
                    if (has_template_arguments(type)
                        and template_of(type) == ^^serde::skip_serializing_if) {
                        // found a specialization
                        // but check to make sure we haven't found
                        // two different ones.
                        if (res != std::meta::info() and res != value_of(A)) {
                            throw "unexpected duplicate";
                        }

                        res = value_of(A);
                    }
                }

                return res;
            }();

            if constexpr (skip_if != std::meta::info()) {
                if (std::invoke([:skip_if:].pred, t.[:M:])) {
                    return;
                }
            }

            obj[field] = boost::json::value_from(t.[:M:]);
        };
    }
}
```
{: data-line="7,22-46" .line-numbers }

At this point, I thought there's another fun approach to solving this problem. With just two attributes, it probably doesn't make sense, but if I were to actually implement all of `serde`, it'd be nice to have an implementation strategy that doesn't just handle each attribute parsing in a vacuum. Instead, what if we were to collect all the attributes into a class type — and then use that class type instead?

Let's see what that looks like.

First, we're going to to create a new class type — `serde::attributes`. We're going to programmatically define it to have a member for each attribute that we have. The tricky part is the type of the member. For an attribute like `rename`, we should use `optional<rename>`. But for `skip_serializing_if`? We don't know what type to use yet, so we're just going to use `optional<info>` here to maintain type erasure. That is, we want to produce this type:

```cpp
struct attributes {
    optional<rename> rename;
    optional<info> skip_serializing_if;
};
```

That code makes use of `std::meta::define_class()`, the single API in P2996 that does code generation. It doesn't do much, but it does enough for here. Note that since we're iterating over all the members of the namespace `serde`, we have to make sure that we exclude `attributes` — which is of course in that namespace:

```cpp
struct attributes;
consteval {
    std::vector<std::meta::info> specs;
    for (auto m : members_of(^^serde)) {
        if (m == ^^attributes or not has_identifier(m)) {
            continue;
        }

        auto underlying = is_type(m) ? m : ^^std::meta::info;
        specs.push_back(data_member_spec(
            substitute(^^std::optional, {underlying}),
            {.name=identifier_of(m)}));
    }

    define_class(^^attributes, specs);
};
```

We can then write a parsing function that consumes the attributes of a non-static data member into an instance of `attributes`. The most annoying part here is simply finding which non-static data member of `attributes` to write into. I'm going to skip that logic for now and jump straight into how we would use the result of all of this work:

```cpp
namespace boost::json {
    template <class T>
        requires (has_annotation(^^T, derive<serde::Serialize>))
    void tag_invoke(value_from_tag const&, value& v, T const& t) {
        auto& obj = v.emplace_object();
        [:expand(nonstatic_data_members_of(^^T)):] >> [&]<auto M>{
            constexpr auto attrs = serde::parse_attrs_from<M>();

            constexpr auto field = attrs.rename
                .transform([](serde::rename r){
                    return std::string_view(r.field);
                })
                .value_or(identifier_of(M));

            if constexpr (attrs.skip_serializing_if) {
                if (std::invoke(
                    [:*attrs.skip_serializing_if:].pred,
                    t.[:M:]))
                {
                    return;
                }
            }

            obj[field] = boost::json::value_from(t.[:M:]);
        };
    }
}
```
{: .line-numbers }

Sure, we moved the most complicated logic (parsing the annotations) into a function, which I'm not including in the above code block. But this is pretty nice right?

You can see the full implementation using this approach [here](https://godbolt.org/z/jaKTe57Gf). As I said, this is a bit overkill when we only have two attributes. But this approach means that all it takes to add a new `serde` attribute is to declare a new class or class template in the namespace and then just use it in the implementation.


## Rust Attributes vs C++ Annotations

In the context of looking at serde, there are two things that stood out to me when comparing the C++ and Rust solutions: syntax and library design.

### Syntax

The first thing which stood out to me most for the syntax difference on the usage side. This was my Rust declaration:

```rust
#[derive(Serialize)]
struct Person {
    #[serde(rename = "first name")]
    first: String,

    #[serde(rename = "middle name", skip_serializing_if = "String::is_empty")]
    middle: String,

    #[serde(rename = "last name")]
    last: String,
}
```

And this was my C++ one:

```cpp
struct [[=derive<serde::Serialize>]] Person {
    [[=serde::rename("first name")]]
    std::string first;

    [[=serde::rename("middle name")]]
    [[=serde::skip_serializing_if(&std::string::empty)]]
    std::string middle = "";

    [[=serde::rename("last name")]]
    std::string last;
};
```

The C++ annotations are... busier, but this is mostly a syntactic question. Rust's are lighter because annotations follow different grammar from the rest of the language — `serde(rename = "first name")`{:.lang-rust} isn't valid Rust, and there is no call to a function named `serde` being performed here. One consequence of this is that the usage side for Rust annotations can be nicer, since it really reads like assigning values to options. And you get some flexibility with how you can use the contents of these "calls", since you can write `#[arg(short)]`{:.lang-rust} or `#[arg(short = 'k')]`{:.lang-rust} as a nice way of indicating that you want the "default" value of `short` as opposed to specifically the value `k` (this is from [clap](https://docs.rs/clap/latest/clap/)).

Now it's tempting to wonder about reusing the (exceedingly oddly specific) attribute `using` syntax and allowing `using serde:` here. But it wouldn't save that much typing at all:

```cpp
struct [[=derive<serde::Serialize>]] Person {
    // old version: 83 chars
    [[=serde::rename("middle name"), =serde::skip_serializing_if(&std::string::empty)]]
    std::string middle = "";

    // new version: 82 chars
    [[using serde: =rename("middle name"), =skip_serializing_if(&std::string::empty)]]
    std::string middle = "";
};
```

The Rust version is only 74 characters. It's not _much_ shorter, but it's at least comfortably on the left side of the 80 column mark.

On the flip side though, it's useful to note what Rust pays for to achieve this. With the C++ annotations design, the annotations are *just* values. There's only a little bit of new grammar to learn (specifically the use of prefix `=`), but other than that you can already see what's going on here. The contents of an annotation aren't some incantation whose meaning is purely defined by the library, they are actual C++ values. Syntax highlighting already does the right thing. It's *just* code. If you don't know what `serde::skip_serializing_if` means, you can just go to its definition.

> Of course, in my simple implementation the definition doesn't tell you anything. It's just a class template with one data member. But in a real library, there would presumably be at least a comment.
{:.prompt-info}

One thing you might have noticed that I did not comment on when going through the implementations of these examples was how to parse the values out of the annotations. This is because I did not need to actually do any parsing at all! The compiler does it for me. The only work I had to do was to parse the annotations I care about from a list of annotations — but that's simply picking out values from a list. There's no actual parsing involved. Rust libraries have to _actually parse_ these token streams. For serde, that's [nearly 2,000 lines of code](https://github.com/serde-rs/serde/blob/31000e1874ff01362f91e7b53794e402fab4fc78/serde_derive/src/internals/attr.rs). That's a lot of logic that C++ annotation-based libraries will simply not have to ever write. And that matters.

> To be fair, `serde` is an older library, and newer Rust has something called [derive macro helper attributes](https://doc.rust-lang.org/reference/procedural-macros.html#derive-macro-helper-attributes) which will make this easier to do. Nevertheless, it is still up to the Rust library to do the kind of parsing that we will not have to do in C++.
>
> Also, I didn't pick `serde` just because it has a particularly large parsing component — I picked it because it's so well-known and widely used as a library that even I, not a Rust programmer, am aware of it.
{:.prompt-info}

Another interesting thing is that while the Rust and C++ approaches here end up doing similar things in different ways, they're not _quite_ the same. With Rust, `#[derive(Debug)]`{:.lang-rust} injects the appropriate `impl` for `Debug`. With the C++ annotations approach, we are _not_ injecting the appropriate specialization of `formatter`, we're just adding a global constrained one.

That means that it _could_, without further work, be ambiguous if I make one small change:

```cpp
struct [[=derive<Debug>]] Point {
    int x;
    int y;

    // let's just make this a range for seemingly no reason
    auto begin() -> int*;
    auto end() -> int*;
};

int main() {
    auto p = Point{.x=1, .y=2};
    std::println("p={}", p); // error: ambiguous
}
```
{: data-line="5-7" .line-numbers }

Well, I'd have to make two small changes. The specialization I originally presented was declared like:

```cpp
template <class T> requires (has_annotation(^^T, derive<Debug>))
struct std::formatter<T> { /* ... */ };
```

but if I instead make it:

```cpp
template <class T, class Char> requires (has_annotation(^^T, derive<Debug>))
struct std::formatter<T, Char> { /* ... */ };
```

then it [becomes ambiguous](https://godbolt.org/z/sbcx6MW85) with the formatter for ranges that I added for C++23. This can be worked around by disabling an extra variable template (which is preprocessed out in the link):

```cpp
template <class T> requires (has_annotation(^^T, derive<Debug>))
inline constexpr auto std::format_kind<T> = std::range_format::disabled;
```

This seems surprising that it's necessary — since again conceptually the C++ approach is the same as the Rust one, and you might expect that adding the annotation injects the very specific, explicit specialization which cannot possibly be ambiguous with anything. It's just that it can't really work like that. So these kind of partial specialization ambiguities will almost certainly be an issue. Perhaps in the future we can come up with a way for annotations like `[[=derive<Debug>]]` to actually inject a specialization to avoid this problem. It certainly seems worth considering.

### Library Design

In Rust's `serde` library, serialization is a two-stage process. The type author opts in to serialization, which emits an implementation that functions sort of like an immediate representation of the type. Then authors of various protocols effectively can implement different backends.

In the implementation for `Person`, Rust emits an `impl` for `serde::Serialize` which takes in an arbitrary type which satisfies `serde::Serializer` (note the extra `r`). We then make a bunch of serialization calls into that `serializer` — which can then do whatever it sees fit with them. Whatever is appropriate for that protocol — whether it's JSON or CBOR or YAML or TOML or ...

A C++-ification of that implementation would look like this (to avoid getting bogged down in error handling, which isn't relevant here, I'm just going to assume these functions throw on error rather than returning a `Result` as they do in Rust):

```cpp
template <Serializer S>
auto serialize(Person const& p, S& serializer) -> void {
    auto state = serializer.serialize_struct(
        "Person",
        2 + (p.middle.empty() ? 0 : 1));
    state.serialize_field("first name", p.first);
    if (not p.middle.empty()) {
        state.serialize_field("middle name", p.middle);
    } else {
        state.skip_field("middle name", p.middle);
    }
    state.serialize_field("last name", p.last);
    state.end();
}
```
{: data-line="4-5,10" .line-numbers }

This is a nice design for the decoupling it allows.

However, you might notice that the C++ implementation I showed earlier doesn't do this at all. Not because I was lazy — but rather because it's completely unnecessary with the existence of introspection. In C++, we didn't need to emit this intermediate representation because we _already_ have it in the form of basic type introspection. The Boost.JSON implementation just does all of the serialization work directly from the data members.

It's not just a matter of writing less code, it's a matter of not even having to deal with this extra layer of abstraction at all. It's not like this layer is computationally expensive, I'm sure it compiles down pretty easily. It's just that it's unnecessary.

Consider the highlighted call to `skip_field` above. For many serialization targets (e.g. JSON), the way to skip serializing a field is simply to *not* serialize it. That's why the default implementation of `skip_field` [does nothing](https://github.com/serde-rs/serde/blob/31000e1874ff01362f91e7b53794e402fab4fc78/serde/src/ser/mod.rs#L1869-L1876) (as you would expect) and `serde_json` does not override it.

Likewise, consider the computation of the number of fields also highlighted above. The JSON serializer doesn't need such a thing either, and simply ignores this value. Ditto the name of the type.

But in creating an intermediate representation — you have to create a representation rich enough to be able to handle all possible (de)serialization targets. Some of them will need the number of fields in advance or will need to leave a hole for skipped fields. So `serde` needs to provide for such.

In C++, we just don't. The serializer for any given target can just directly do all the operations that it needs to do — because it directly has all the information at this disposal. No abstraction necessary. As a result, the C++ equivalent of the `serde` library would probably just be a list of types usable as annotations, the `parse_attrs_from()` function, and maybe a couple other little helpers.

Introspection is a pretty powerful tool.

## This is not the End

I wanted to end by pointing out that there are a few language features, in different languages, that are somewhat closely related:

* Rust's procedural macros
* Python decorators
* Herb Sutter's metaclasses proposal

All of them involve writing code — and then passing that code into a function to produce new code. Metaclasses and decorators actually replace the original code, whereas the derive macro only injects new code (although other procedural macros can also replace).

The annotation proposal looks, in spirit, related to these — but it's a very different mechanism and shouldn't be confused for them. It's not injecting code at all, it's simply enhancing introspection abilities.

Which isn't to say that annotations aren't useful! As I've hopefully demonstrated, it promises to be an incredibly useful facility that allows for writing the kinds of user-friendly library APIs that were unthinkable in C++ before now.

But this is only the beginning.
