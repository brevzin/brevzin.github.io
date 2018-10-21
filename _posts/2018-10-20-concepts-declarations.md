---
layout: post
title: "Declarations using Concepts"
category: c++
tags:
 - c++
 - c++20
 - concepts
--- 

One of my all-time favorite C++ talks is Ben Deane's [Using Types Effectively](https://www.youtube.com/watch?v=ojZbFIQSdl8) from CppCon 2016. I like it for a lot of reasons, but for the purposes of this post - I really like the game Ben plays (starting at around the 29m mark) where he gives a function signature of a _total_ function template - just the signature, no names attached whatsoever - and asks you to name the function. This seems like a really difficult task, we often talk about how names are important, and here we have no names at all - no names for functions or for arguments.

And yet... here's one example:

```cpp
template <typename K, typename V>
optional<V> f(map<K,V>, K);
```

Not only do we know what this function does, but we even know how to implement it. That's the power we get from using types effectively. 

I think it's a worthwhile goal, in of itself, to try to write function declarations in a way to achieve this kind of clarity. Not only does the clarity tell the reader what the function does - but it even tells the implementer how to implement it!

But it turns out, even in C++20 with Concepts, it's not really possible. 

This post will go through several examples of functions that you just cannot declare in this kind of clear, effective way. The examples I'm taking are all from the function programming domain - I'm not choosing them because FP is particularly complex, I'm actually choosing them because they're actually _not_ complex but the tools we have at our disposal make them seem so.

### `fmap` over `vector<T>`

What we want to do is to write a function template that takes:
- a `vector<T>`, for any `T`
- a function that you can call with a `T` and, when you do, gives you back some type `U`. From here on out, I'll appropriate Haskell's syntax here and say that we want a function like `T -> U`.

and returns a `vector<U>`. In Python, this function is called `map()`. In C++, it's the `transform()` algorithm. How do we declare this in C++20?

Let me first start with a lot of non-solutions. 

Many people will try to write the following. I have seen it dozens of times on StackOverflow. I have seen it in blogs about function programming. I have seen it in talks. I have seen it in a book. I think this is such a common thing to reach for because it just looks so obviously correct. What's the easiest way to write a function `T -> U`? This:

```cpp
template <typename T, typename U>
vector<U> fmap(function<U(T)>, vector<T>);
```

To really quickly explain why this is wrong: template deduction doesn’t allow for conversions. If I wanted to pass a function pointer or a lambda into this, that would fail, because that function pointer/lambda is not literally a `std::function`. Hence deduction fails. Even if it did work, it’d also be very inefficient, since we’re imposing type erasure in a place where we don’t actually need it.

But on the other hand, there is something very nice about that right? We have this clear `T` to `U` relationship up there, which we really want. It's very clear where the types are coming from. I completely understand why so many people reach for this. Even, ahem, Ben in that talk.

Using `std::function` is out. But Concepts does give us a better way to constrain types, and Ranges gives us a concept that we can use here: `Invocable`. This leads us to the next non-solution:

```cpp
template <typename T, Invocable<T> F>
auto fmap(F, vector<T>);
```

If you have not seem the _partial-concept-id_ syntax yet, the above is just a very nice shorthand for:

```cpp
template <typename T, typename F>
    requires Invocable<F, T>
auto fmap(F, vector<T>);
```

This works, in the sense that it correctly and properly constrains our arguments. But... we're just returning `auto`. What does this function actually do? It could do _anything_. Don't believe me? There are quite a lot of algorithms that take a range and a unary function (which is all we know about this callable). This could be `all_of()` (or `any_of()`/`none_of()`). This could be `find_if()`. Or `count_if()`. Or `for_each()`. Or ... The point is, we want our declarations to convey complete information about the function and this just doesn't. This lack is part of why I am generally skeptical about `auto` returns in many cases.

The next non-solution isn't actually valid C++20 code yet, it is just a proposal. [P1168](https://wg21.link/p1168) allows for using class template argument deduction in the return type. Which would allow:

```cpp
template <typename T, Invocable<T> F>
vector auto fmap(F, vector<T>);
```

This is better, but to me is still insufficient. What kind of `vector` does it return? This could still be an algorithm like `filter()` if it returned a `vector<T>` (though presumably we'd actually use `T` in that case). It could also be monadic `bind()` if the function `F` returned some `vector<U>` (instead of `U`) and the full function template did as well. It's not as clear as it could be. 

What's the actual solution?

The best we can do in C++20, with Concepts, with Ranges, is:

```cpp
template <typename T, Invocable<T> F>
vector<invoke_result_t<F,T>> fmap(F, vector<T>);
```

This is kind of a mouthful, and isn't really that clear. The ultimate problem is that Concepts are just predicates. A `concept` takes a bunch of types (or values or templates) and just tells you yes or no (plus some other details for subsumption purposes). That's it. In our example here, we want to have a function `T -> U`. Concepts can give us the `T ->` part. That's just a check. But it cannot give us the `-> U` part, that's a more complex query. For that we need type traits - in this case `invoke_result`. It's pretty unsatisfying that we need two different tools to pick out the two different parts. And you just have to a priori know where to find these tools. 

Even more so because `invoke_result` is specified to be SFINAE-friendly, so the use of the concept behaves, in some sense, like a glorified comment. I might even write the above as:

```cpp
template <typename T, typename F,
    typename U = invoke_result_t<F,T>>
vector<U> fmap(F, vector<T>);
```

In some sense, that's better than the concepts solution. Which seems wrong - concepts are supposed to be the way we constrain function templates.

Let's go deeper.

### `fmap` over a `Range`

Whenever we talk informally about algorithms taking ranges, we tend to say that it takes a `Range` of `T`s and then does something with those `T`s. But we can't say `Range` of `T`s in the same way that we can't say `T -> U`. We can only say `Range`. 

How, then, do we generalize our `fmap` example above to take an arbitrary range of `T`s instead of specifically a `vector<T>`? We could write this:

```cpp
template <Range R, Invocable<iter_value_t<iterator_t<R>>> F>
vector<invoke_result_t<F, iter_value_t<iterator_t<R>>>> fmap(F, R);
```

Though we'd probably want to pull out that commonality:

```cpp
template <Range R,
    typename T = iter_value_t<iterator_t<R>>, 
    Invocable<T> F>
vector<invoke_result_t<F, T>> fmap(F, R);
```

Or, repeating what I did above:

```cpp
template <Range R,
    typename T = iter_value_t<iterator_t<R>>, 
    typename F,
    typename U = invoke_result_t<F, T>>
vector<U> fmap(F, R);
```

This is very unsatisfying to me. 

### `bind` over `vector<T>`

Let's take a different algorithm. Monadic `bind()` doesn't have a direct analogue in the C++ standard library, and I'm not going to go into all the functional programming and category theory details behind it. Suffice it to say that we want a function that takes:

- a `vector<T>`, for any `T`
- a function `T -> vector<U>`

And returns `vector<U>`. The two differences with `fmap` are that the function must return some kind of `vector` (instead of anything) and that the return type is the return type of the callable (instead of being a `vector` of its return type). In other words, `fmap` taking a `vector<int>` and a `int -> vector<double>` returns a `vector<vector<double>>` while `bind` returns a `vector<double>`. There's that extra unwrapping step that happens (which in Haskell is called `join`).

Now we need two layers of constraints. Which is fine, Concepts can constrain very well:

```cpp
template <typename T, template <typename...> class Z>
concept Specializes = /* ... */;

template <typename T,
        Invocable<T> F,
        typename U = invoke_result_t<F, T>>
    requires Specializes<U, vector>
U bind(F, vector<T>);
```

which I _think_ we can shorten to:

```cpp
template <typename T,
        Invocable<T> F,
        Specializes<vector> U = invoke_result_t<F, T>>
U bind(F, vector<T>);
```

Is that clear? Note that the fact that this function returns some kind of `vector` is an extremely important part of its interface, but you cannot tell here because we're returning `U`. We could go a very circuitous route in order to really make it explicit - by returning <code class="language-cpp">vector&lt;typename U::value_type&gt;</code>. But I'm not sure that would be better.

### `sequence` over a `Range` of `expected<T,E>`

Okay, one more. There's a function in Haskell called `sequence`. In C++ terms, it takes a `vector<expected<T,E>>` and returns a `expected<vector<T>, E>`. That declaration in C++ is easy:

```cpp
template <typename T, typename E>
expected<vector<T>, E> sequence(vector<expected<T, E>>);
```

This is the kind of declaration that is very nice and clear. But what if we wanted an arbitrary range over `expected`s instead of specifically a `vector`? Maybe this?

```cpp
template <Range R,
    Specializes<expected> V = iter_value_t<iterator_t<R>>>
expected<
    vector<typename V::value_type>,
    typename V::error_type
> sequence(R);
```

Compare this declaration to the `vector` declaration above it. This is a dramatic difference in clarity - much larger than the conceptual difference between the two algorithms really suggests.

### So... what do we do?

What I think we really need is two things:

1. Concepts need a way to expose their _associated types_
2. We need a way to do template-style pattern matching within a template declaration

You can see in these examples that concepts often have more information associated with them than just a predicate. `Invocable` is closely associated with the actual result of that invocation - you almost always really need that extra type. `Range` is closely associated with the value type that this range is over - you almost always need that too. It would be great if we could express that relationship directly, so you don't just need to magically know how you could get that information.

You can also see in these examples that it would be really helpful to do template-style pattern matching as part of the constraint process. The difference between the `vector` and `Range` version of `sequence()`, for instance, is all about the difference between being able to pattern-match on `vector<expected<T,E>>` versus having to very explicitly spell out what this means for the `Range` version.

I would love to see something like this:

```cpp
template <typename T,
    Invocable<T> F /* whose result_type is U */>
vector<U> fmap(F, vector<T>);

template <Range R /* whose value_type is T */,
    Invocable<T> F /* whose result_type is U */>
vector<U> fmap(F, R);

template <typename T,
    Invocable<T> F /* whose result_type is vector<U> */>
vector<U> bind(F, vector<T>);

template <typename R /* whose value_type is expected<T,E> */>
expected<vector<T>, E> sequence(R);
```

Compare these 4 declarations to the ones I presented earlier. These are _dramatically_ clearer. We only need to know one thing: the concept. And we can directly express the constraints we want in code, in the way we think about them. 

I don't know how to get there syntactically. There are lots of pieces that you need:

- Concepts need to be able to declare associated types.
- Template declarations need an easy way to pull out those associated types.
- That pulling out process needs to be able to either introduce new names or use existing names somehow (hypothetically `Predicate<T>` could be spelled `Invocable<T>` whose `result_type` is `Boolean` - and you need a way to differentiate between using the concept `Boolean` and introducing a new name).
- And that pulling out process needs to itself be a kind of constraint that you can add

I have no good proposal for any of these. But I'm hoping that somebody reads this, agrees that this is a real problem, and comes up with one!