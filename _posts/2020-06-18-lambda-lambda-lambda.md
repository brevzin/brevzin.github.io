---
layout: post
title: "Lambda Lambda Lambda"
category: c++
tags:
  - c++
  - lambda
---

I like watching Conor Hoekstra's videos, both because he's generally an engaging presenter, and also because he talks about lots and lots and lots of programming languages. I don't know that many languages, so it's nice to get exposure to how different languages can solve the same problem.

A [recent video](https://www.youtube.com/watch?v=pDbDtGn1PXk) of his discussed a fairly simple problem (how to count the number of negative numbers in a matrix) and he went through like a dozen languages' implementations of it. What all languages had to do was have _some_ mechanism of determining whether a number is negative - which for most involves using a lambda (sometimes called an anonymous function).

What I found especially interesting is how all the different languages lambdas looked, and I wanted to focus on that specifically. How, in a given language, would you write a lambda expression for checking if a given number is negative?

```cpp
(<0)                              // 4:  Haskell
_ < 0                             // 5:  Scala
_1 < 0                            // 6:  Boost.Lambda
#(< % 0)                          // 8:  Clojure
&(&1 < 0)                         // 9:  Elixir
|e| e < 0                         // 9:  Rust
\(e) e < 0                        // 10: R 4.1
{ $0 < 0 }                        // 10: Swift
{ it < 0 }                        // 10: Kotlin
e -> e < 0                        // 10: Java
e => e < 0                        // 10: C#, JS, Scala
\e -> e < 0                       // 11: Haskell
{ |e| e < 0 }                     // 13: Ruby
{ e in e < 0 }                    // 14: Swift
{ e -> e < 0 }                    // 14: Kotlin
fun e -> e < 0                    // 14: F#, OCaml
lambda e: e < 0                   // 15: Python
(λ (x) (< x 0))                   // 15: Racket
fn x -> x < 0 end                 // 17: Elixir
(lambda (x) (< x 0))              // 20: Racket/Scheme/LISP
[](auto e) { return e < 0; }      // 28: C++
std::bind(std::less{}, _1, 0)     // 29: C++
func(e int) bool { return e < 0 } // 33: Go
```

For the languages that require braces, I'm counting the braces (whether that's fair or not). Also, Clojure can use `%1` instead of `%`.

And yes, note that Boost.Lambda and `std::bind` are in that list (and assume you have the appropriate `using namespace` declaration in scope for the placeholders).

I think this is an interesting table, just in of itself. It basically shows that there are really three kinds of lambdas here:

1. Fully anonymous functions (those lambdas that take some kind of list of parameters and then have a separate body, as in C++ or Java or ...)
2. Placeholder expressions (those that are a single expression with special placeholders, as in Scala or Clojure or Boost.Lambda or ...). Swift seems unique in this regard in using `$0` for the first parameter, all the other languages and libraries I'm familiar with start counting at `1`. 
3. Partial function applications (technically not actually lambdas but solve the same problem so close enough, as in Haskell or `std::bind`)

Several languages have multiple options here as well.

Notably, C++'s lambda here is nearly the longest lambda. The original version of this post had it at the top until Eugene Yakubovich pointed out the Golang lambda to me - which is somewhat surprising since C++'s lambdas are long due to the fundamental complexity of C++ - what's Go's excuse? So that's cool. Technically not last!

If anything though, this is a favorable comparison for C++ because we're both taking a value and returning a value. If we needed to take a reference, that's either `auto const&` or `auto&&` (7 or 2 characters longer). And if we want to return a reference instead of a value? Slap on `-> decltype(auto)` for a bonus 17 characters, itself as long as every other lambda on there. 

C++'s lambdas have three portions that are unique, or mostly unique, amongst this language set:

1. A specified capture. Rust, for instance, allows you to capture by `move`, writing `move |needle| haystack.contains(needle)`{:.language-rust}. As pointed out on reddit by user Nobody_1707, [Swift](https://docs.swift.org/swift-book/ReferenceManual/Expressions.html#ID544) also has captures that are quite similar to C++'s. But beyond that, I'm not sure if any of the other languages even have a notion of capture at all. You basically just get `[&]`. That said, given that C++ isn't garbage collected, I'm not sure there is a good default for capture beyond `[]` - and at that point we're not exactly saving a lot of characters.

2. A mandatory parameter declaration. In many of the other statically typed languages, you _can_ provide a type annotation - but it is _optional_. Again with Rust, the example could've been `|e: i32| e < 0`{:.language-rust} just like with Scala, it could've been `(e: Int) => e < 0`. But the key point is that the parameter declaration is a choice. And in the simple cases, you would likely avoid the type, while in more complicated cases, you would likely prefer to keep it.

3. The `return` keyword. In the other languages, we just have an expression.

One of the proposals I had tried to pursue, [P0573](https://wg21.link/p0573), would have  created a new form of "fully anonymous function" that makes the parameter declaration optional and omits the `return` keyword. That paper suggested:

```cpp
[](e) => e < 0                // P0573R2: 14
[](auto e) { return e < 0; }  // C++: 28
```

That gives us half the length. Still longer than most other languages, but substantially better. However, this proposal was rejected for some notable reasons: both the differing parse issue (ambiguous for humans with unnamed parameters) and the meaning of the return type. See [my earlier post]({% post_url 2020-01-15-abbrev-lambdas %}) on the topic. I think part of the reason removing the type annotation is difficult for C++ specifically is that our parameter declarations are of the form `Type name` while a lot of these other languages write them as `name: Type` - the latter just lends itself better to omitting the type and keeping the focus on the name (and doesn't allow for unnamed parameters, which is the crux of the C++ issue, and has never struck me as an especially important feature anyway).

I think, as such, a novel syntax for "fully anonymous function" is probably not on the table - I don't see how you overcome those two issues (although for the third issue presented there, [P2036](https://wg21.link/p2036) was very favorably received in Prague and seems likely to be accepted as a defect) with a syntax that looks something like C++'s lambdas. Introducing a _different_ syntax for full lambdas seems undesirable to me at the moment (and would still have the `auto` vs `decltype(auto)` question anyway).

But that leaves open the question of the placeholder expressions. I had originally somewhat derided that style as harder to read than a full anonymous function style. But for the simple cases, I'm not so sure anymore. As `vector<bool>` points out in [Now I Am Become Perl](https://vector-of-bool.github.io/2018/10/31/become-perl.html), there's a difference between initial confusion and permanent confusion (before going on to present some syntax suggestions that certainly cause initial confusion). But what he points out there is precisely this idea of a placeholder expression lambda.

What might that syntax look like? Well, we still want to preserve the notion of capture - I think that's still an important concept in C++ and we need an introducer anyway. The reason for this is, consider: `f(_1)`. What would that mean?

```cpp
f([](auto&& x, auto&&...) -> decltype(auto) { return (x); })
```
or
```cpp
[](auto&& x, auto&&...) -> decltype(auto) { return f(x); }
```

If it's context dependent... well, how do you decide? Seems like a hard question. I'm not entirely sure how Scala does it, to be honest. Clojure, Elixir, and Swift have clear markers for where the lambda starts. And I don't think we can really uses braces here - as in `{ f(_1) }`.

Maybe then we have the introducer, followed by some kind of punctuator, followed by an expression?

```cpp
[] => _1 < 0
[] -> _1 < 0
[]: _1 < 0
```

It's certainly different, but it's basically the same thing we had in Boost.Lambda (just liable to produce staggeringly better code).

There's an example in the HOPL paper demonstrating STL:

```cpp
vector<string>::iterator p =
    find_if(v.begin(), v.end(), Less_than<string>("falcon"));
```

Consider the shape of the function object here - it's a partial function application. Exactly what we would write in Haskell - `(< "falcon")` (semantically, anyway). Björn Fahller has a whole [repo](https://github.com/rollbear/lift) full of function objects that support partial function application like this, only difference his version drops the type:  `less_than("falcon")`.

Now, what would the equivalent C++ lambda be?
```cpp
[](std::string const& s) { return s < "f"; } // 44: C++11
[](auto&& s) { return s < "f"; }             // 32: C++14
lift::less_than("f")                         // 20: with lift 
```

This right here is why I frequently write generic lambdas even in cases where I only need a monomorphic one. I had to shorten the string because the lambda was too wide to fit in my blog! Thank you, Faisal!

If that style is good enough for two very different people with very different programming styles (despite having most of the same letters in their first names), maybe parameter names are overrated anyway? I mean, it sure reads pretty nice: `find_if(..., less_than(...))` is pretty good English. Is it really any different if we use the operator instead of the words?

```cpp
(<"f")                           // 6: Haskell
[]: _1 < "f"                     // 12: placeholder?
lift::less_than("f")             // 20: with lift 
[](auto&& s) { return s < "f"; } // 32: C++14
```

I could get used to this. This doesn't strike me as a source of permanent confusion.

Of course, this being C++, there's a lot of other questions to consider. Like how do you deal with forwarding (use a macro) or how do you deal with variadic arguments (I don't know) or what's the arity of these lambdas, is it based on the largest placeholder present (no) or would you still want [P0834](https://wg21.link/p0834) with this (good question) or a shorter form of specifiying operator functions as suggested in [P0119](https://wg21.link/p0119) (yes, specifically the `(>)` syntax as a shorter way to write `std::greater()`).

But that's a huge digression from the main point of this post, which is quite simply: C++ has really, really long lambdas.
