---
layout: post
title: "Concept template parameters 2"
category: c++
series: concept templates
tags:
 - c++
 - c++20
 - concepts
--- 

A few months ago, I wrote a post with some motivating examples, and I just wanted to add some more to the list.

### `RangeOf`{:.language-cpp}

Sometimes, we want to write an algorithm that takes a range of some specific type. Say, we want to operate specifically over `int`{:.language-cpp}s. We can do that:

```cpp
template <typename R, typename T>
concept RangeOfSame = Range<R> && Same<range_value_t<R>, T>;

int some_algo(RangeOfSame<int> auto&&);
```

I'm not sure if `range_value_t` will be in C++20 or not. If not, it can be spelled `value_type_t<iterator_t<R>>`{:.language-cpp}. In any case, this is fine. It works, it's pretty clear.

But sometimes, the underlying condition we want isn't exactly that it's the _same_ type - maybe we want something convertible? For instance, if I'm writing my own `vector` class, I might want it to be constructible from any range _convertible to_ the same value type right? That's also pretty easy to write with concepts:

```cpp
template <typename R, typename T>
concept RangeOfConvertible = Range<R> &&
    ConvertibleTo<range_value_t<R>, T>;

template <typename T>
struct my_vector {
    my_vector(RangeOfConvertible<T> auto&&);
};
```

Again, this is fine. It works, it's pretty clear. But then it's easy to keep coming up with situations where you want slightly different mechanics. Maybe you go back to the original algorithm and it's not really specific to `int`{:.language-cpp}s and you want to generalize it to arbitrary numeric types? Do you write a new concept then?

```cpp
template <typename R>
concept RangeOfNumeric = Range<R> &&
    Numeric<range_value_t<R>>

Numeric auto some_algo(RangeOfNumeric auto&&);
```

You probably see where I'm going with this. All of these concepts are the same - or least they could be the same if we could factor out what constraint we're performing on the value type of the range:

```cpp
template <typename R, template <typename> concept C>
concept RangeOf = Range<R> && C<range_value_type_t<R>>;

int some_algo_ints(RangeOf<Same<int>> auto&&);
Numeric auto some_algo(RangeOf<Numeric>> auto&&);

template <typename T>
struct my_vector {
    my_vector(RangeOf<ConvertibleTo<T>> auto&&);
};
```

Seems very useful.

### `Lvalue`{:.language-cpp}

One of the concepts that we're getting in C++20 is [`Invocable`{:.language-cpp}](http://eel.is/c++draft/concept.invocable):

```cpp
template<class F, class... Args>
  concept Invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...);
  };
```

But this has an interesting effect when we try to use it, particularly when using terse syntax:

```cpp
void call_with_42(Invocable<int> auto&& f) {
    f(42);
}
```

Is this a properly constrained function template? It's actually not. If we spell out this function template with a longer form syntax, it might be easier to see:

```cpp
template <typename F>
    requires Invocable<F, int>
void call_with_42(F&& f) {
    f(42);
}

struct RvalueOnly {
    void operator()(int) &&;
};

call_with_42(RvalueOnly{}); // error
```

That call fails, but it doesn't fail the concept check - we deduce `F` as `RvalueOnly`, and `Invocable<RvalueOnly, int>`{:.language-cpp} is satisfied... but then `f(42)`{:.language-cpp} actually invokes the function as an lvalue, so it's the wrong check.

In order to fix this, we'd have to either use the longest-form syntax with `Invocable`:

```cpp
template <typename F>
    requires Invocable<F&, int>
void call_with_42(F&& f);
```

or we could add a new concept, which allows all the syntax forms:

```cpp
template <typename F, typename... Args>
concept LvalueInvocable = Invocable<F&, Args...>;

template <typename F>
    requires LvalueInvocable<F, int>
void call_with_42_long(F&& f);

template <LvalueInvocable<int> F>
void call_with_42_medium(F&& f);

void call_with_42_terse(LvalueInvocable<int> auto&& f);
```

Or... we could just wrap the concept to provide a more general solution (since this problem will be hardly specific to `Invocable`):

```cpp
template <typename T, template <typename> concept C>
concept Lvalue = C<T&>;

// I probably wouldn't use the adapted concept
// in the long form syntax
template <typename F>
    requires Invocable<F&, int>
void call_with_42_long(F&& f);

// ... but it would allow both the medium syntax
template <Lvalue<Invocable<int>> F>
void call_with_42_medium(F&& f);

// ... and the terse form
void call_with_42_terse(Lvalue<Invocable<int>> auto&& f);
```
