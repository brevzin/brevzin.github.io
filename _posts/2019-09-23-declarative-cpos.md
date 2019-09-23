---
layout: post
title: "Declaratively implementing CPOs"
category: c++
tags:
  - c++
  - c++20
---

I like a declarative approach to programming. Ben Deane has given several good talks on what declarative programming is (such as [this one](https://www.youtube.com/watch?v=2ouxETt75R4) from CppNow 2018), and if you haven't seen them, you should. The idea is to try to write your logic using expressions and to make it correct by construction, rather than using statements and having to reason imperatively.

One of the new design patterns in C++20 is something known as a _customization point object_, or CPO. A CPO is a callable function object, which means you can easily pass it around to other functions without having to worry about the struggle that is passing around other kinds of polymorphic callables (like function templates and overload sets). A CPO also can be (but isn't necessarily) a customization point and handles the customization selection for you so that you can just always directly invoke it. Basically, it's state of the art library design for doing generic programming, because the language still isn't helping us out here. 

One of the new CPOs from Ranges is `std::ranges::begin`{:.language-cpp}, specified in [\[range.access.begin\]](http://eel.is/c++draft/range.access.begin). `ranges::begin(E)`{:.language-cpp} is expression-equivalent to one of the following, in sequential order:

1. `E+0`{:.language-cpp} if `E`{:.language-cpp} is an lvalue array
2. `decay_copy(E.begin())`{:.language-cpp} if `E` is an lvalue, that expression is valid, and its type models `input_or_output_iterator`
3. `decay_copy(begin(E))`{:.language-cpp} if that expression is valid, its type models `input_or_output_iterator`, and overload resolution is performed in a context that includes some poison-pill overloads (I will not go into the details of why poison-pills exist here).

If none of those work, the call is ill-formed (Note that `decay_copy(E)`{:.language-cpp} is what happens when you do `auto x = E;`{:.language-cpp}, see also [P0849](https://wg21.link/p0849)).

Here's the question: how do we implement `ranges::begin`{:.language-cpp}? And, moreover, how do we implement this _declaratively_? 

My solution is quite similar to what I went through in [Higher Order Fun]({% post_url 2018-09-23-higher-order-fun %}), so let's just use Boost.Hof for this (I'm assuming a `FWD` macro for sanity):

```cpp
namespace impl {
  template <typename T> void begin(T&&) = delete;
  template <typename T> void begin(std::initializer_list<T>&&) = delete;
  
  template <typename T>
  concept decays_to_iterator = std::input_or_output_iterator<
    std::decay_t<T>>;
  
  inline constexpr auto fn = boost::hof::first_of(
    // 1. lvalue array case
    []<typename T, size_t N>(T (&arr)[N]) noexcept
    {
        return arr;
    },
    // 2. member case
    [](auto&& rng)
        noexcept(noexcept(rng.begin()))
        requires
          std::is_lvalue_reference_v<decltype(rng)> &&
          decays_to_iterator<decltype(rng.begin())>
    {
        return rng.begin();
    },
    // 3. non-member case
    [](auto&& rng)
        noexcept(noexcept(begin(FWD(rng))))
        requires decays_to_iterator<
            decltype(begin(FWD(rng)))>
    {
        return begin(FWD(rng));
    }
  );
}

inline constexpr auto begin = impl::fn;
```

The member case needs to take a forwarding reference even though it requires an lvalue reference because a const rvalue can still bind to an `auto&`{:.language-cpp} parameter. The array case actually has the same problem (it accidentally accepts rvalue const arrays), but I'm going to punt on this problem until later. I will get back to it.

Other than the array problem, this is actually a complete implementation (it's `constexpr`{:.language-cpp}-correct too!). And I would argue it is pretty easy to just go through and convince yourself it's a correct implementation. We have the three cases laid out in order, the first one of those that works is the one that gets invoked - which is precisely how `ranges::begin`{:.language-cpp} is specified. 

I think that's pretty neat. Declarative style for the win.

Let's make it more complicated.

### Reject rvalues

I will have a paper in the pre-Belfast mailing which proposes to change how `ranges::begin`{:.language-cpp} is specified. The details aren't super relevant for the purposes of this blog post, but the new specification I want is that `ranges::begin(E)`{:.language-cpp} is expression-equivalent to:

1. If `E` is an rvalue, `ranges::begin(E)`{:.language-cpp} is ill-formed.
2. `E+0`{:.language-cpp} if `E`{:.language-cpp} is an array
3. `decay_copy(E.begin())`{:.language-cpp} if that expression is valid, and its type models `input_or_output_iterator`
4. `decay_copy(begin(E))`{:.language-cpp} if that expression is valid, its type models `input_or_output_iterator`, and overload resolution is performed in a context that includes the same poison-pill overloads.

Basically the only difference is that first step: to reject rvalues. That makes things a bit tricker. How do we go about implementing it? How can we reject the rvalues?

One solution, as always, is to just wrap it in a lambda:

```cpp
namespace impl {
  template <typename T> void begin(T&&) = delete;
  template <typename T> void begin(std::initializer_list<T>&&) = delete;
  
  template <typename T>
  concept decays_to_iterator = std::input_or_output_iterator<
    std::decay_t<T>>;
  
  // inner function object that handles steps 2-4
  inline constexpr auto base = boost::hof::first_of(
    // 2. lvalue array case
    []<typename T, size_t N>(T (&arr)[N]) noexcept
    {
        return arr;
    },
    // 3. member case (doesn't have to constrain on lvalue ref)
    [](auto& rng)
        noexcept(noexcept(rng.begin()))
        requires decays_to_iterator<
            decltype(rng.begin())>
    {
        return rng.begin();
    },
    // 4. non-member case
    [](auto& rng)
        noexcept(noexcept(begin(rng)))
        requires decays_to_iterator<
            decltype(begin(rng))>
    {
        return begin(rng);
    }
  );
  
  // 1. outer lambda that constrains on lvalues
  inline constexpr auto fn =
    [](auto&& rng)
        noexcept(noexcept(fn(rng)))
        -> decltype(fn(rng))
        requires std::is_lvalue_reference_v<decltype(rng)>
    {
      return fn(rng);
    };
}

inline constexpr auto begin = impl::fn;
```

This works, and is actually even more correct than the previous implementation (now I'm correctly excluding rvalue const arrays), but I kinda hate it. I no longer have an implementation that mirrors the sequential nature of the specification, and I really liked that aspect of the previous solution - this one is kinda backwards.

Let's try again and use `boost::hof::first_of`{:.language-cpp} for the whole thing:

```cpp
namespace impl {
  template <typename T> void begin(T&&) = delete;
  template <typename T> void begin(std::initializer_list<T>&&) = delete;
  
  template <typename T>
  concept decays_to_iterator = std::input_or_output_iterator<
    std::decay_t<T>>;
  
  // can't delete the call operator of a lambda
  // so resort to a struct instead
  struct reject_rvalues {
    template <typename T>
      requires std::is_rvalue_reference_v<T&&>
    void operator()(T&&) const = delete;
  };
  
  inline constexpr auto fn = boost::hof::first_of(
    // 1. reject rvalues
    reject_rvalues{},
    // 2. array case
    []<typename T, size_t N>(T (&arr)[N]) noexcept
    {
        return arr;
    },
    // 3. member case
    [](auto& rng)
        noexcept(noexcept(rng.begin()))
        requires decays_to_iterator<
            decltype(rng.begin())>
    {
        return rng.begin();
    },
    // 4. non-member case
    [](auto& rng)
        noexcept(noexcept(begin(rng)))
        requires decays_to_iterator<
            decltype(begin(rng))>
    {
        return begin(rng);
    }
  );
}

inline constexpr auto begin = impl::fn;
```

The advantage of this implementation is that I'm back to having a nice, linear order of steps that exactly mirrors the specification. The disadvantage of this implementation is that this doesn't actually work at all.

The way `boost::hof::first_of`{:.language-cpp} works is it finds the first callable that is invocable, and invokes it. If there is no such callable, then the whole thing isn't invocable. But the whole point of `= delete`{:.language-cpp} is to make things _not_ invocable. We end up skipping the `reject_rvalues{}`{:.language-cpp} callable for all arguments, because it's not invocable, so it would never be selected, so it may as well not even be there. 

In other words, `= delete`{:.language-cpp} isn't propagated here. Which is a good thing, because typically we wouldn't actually want it to and that would certainly break our intuition of how `first_of` works. But in this very specific case, we do want to propagate `= delete`{:.language-cpp}. How do we do that?

I think the best way is to get `first_of` in on the act. It needs to be able to differentiate between the deleted overloads that just mean not invocable and the deleted overloads that are intended to propagate, and we can do that by just introducing a special tag type that means "propagate deletion." To do _that_, we need to implement our own `first_of`.

Assuming C++20, and taking a simplified view where we only care about the `const`{:.language-cpp} call operator:

```cpp
template <typename... Fs>
class first_of
{ };

template <typename... Fs>
first_of(Fs...) -> first_of<Fs...>;

template <typename F, typename... Fs>
class first_of<F, Fs...>
{
private:
    using Rest = first_of<Fs...>;
    [[no_unique_address]] F first;
    [[no_unique_address]] Rest rest;
    
public:
    constexpr first_of(F f, Fs... fs)
        : first(std::move(f))
        , rest(std::move(fs)...)
    { }
    
    template <typename... Args,
        bool First = std::is_invocable_v<F const&, Args...>,
        typename Which = std::conditional_t<First, F, Rest> const&>
    constexpr auto operator()(Args&&... args) const
        noexcept(std::is_nothrow_invocable_v<Which, Args...>)
        -> std::invoke_result_t<Which, Args...>
    {
        if constexpr (First) {
            return std::invoke(first, FWD(args)...);
        } else {
            return std::invoke(rest, FWD(args)...);
        }
    }
};
```

We need C++20 for two things here: `[[no_unique_address]]`{:.language-cpp} to ensure that we're not taking up any extra space in the happy case where all of these function objects are empty, and `std::invoke`{:.language-cpp} becoming `constexpr`{:.language-cpp}.

The primary specialization here is empty because it's actually the base case of the recursion we're doing. It has no call operator, so it'll never be callable. The one call operator we have picks between `F` and `Rest`, preferring `F`, to see which callable to try to invoke, and is SFINAE-friendly based on both.

Now, in order to propgate deletion, let's just introduce a specific tag type:

```cpp
struct deleted_t { };
```

And say that if a callable is (a) invocable with a given set of arguments and (b) returns `deleted_t`, then we propagate that deletion and make our call operator deleted as well. We can get this done with the help of a third C++20 feature, this one much bigger and more publicized than the previous two: Concepts. 

One of the two tiebreakers that are added is that one function candidate beats another if it is _more constrained than_ it. The trivial way this happens is if one candidate has any constraints at all and the other does not (a constraint is using a `concept`{:.language-cpp} in any of the syntax forms), and the more complex way is if the constraints of one _subsume_ the constraints of the other. In our example, we don't need to care about subsumption, so I'm not going to get into it. The key is that if we add a constrained overload, it'll win in overload resolution, and that's precisely what we need to happen here:

```cpp
// special tag indicating to propagate = delete
struct deleted_t { };

template <typename... Fs>
class first_of
{ };

template <typename... Fs>
first_of(Fs...) -> first_of<Fs...>;

template <typename F, typename... Fs>
class first_of<F, Fs...>
{
private:
    using Rest = first_of<Fs...>;
    [[no_unique_address]] F first;
    [[no_unique_address]] Rest rest;
    
public:
    constexpr first_of(F f, Fs... fs)
        : first(std::move(f))
        , rest(std::move(fs)...)
    { }
    
    template <typename... Args,
        bool First = std::is_invocable_v<F const&, Args...>,
        typename Which = std::conditional_t<First, F, Rest> const&>
    constexpr auto operator()(Args&&... args) const
        noexcept(std::is_nothrow_invocable_v<Which, Args...>)
        -> std::invoke_result_t<Which, Args...>
    {
        if constexpr (First) {
            return std::invoke(first, FWD(args)...);
        } else {
            return std::invoke(rest, FWD(args)...);
        }
    }
    
    template <typename... Args>
        requires std::invocable<F const&, Args...> &&
            std::same_as<
                std::invoke_result_t<F const&, Args...>,
                deleted_t>
    void operator()(Args&&...) const = delete;
};
```

Let's go over why this works by looking at the second overload - the new one we just added. If it's not a viable candidate (that is, either `F` isn't invocable with these arguments or it doesn't return `deleted_t`), then it's not considered and we're back to exactly where we were before. If it _is_ a viable candidate, then we're in a situation where both candidates are necessarily viable. If `F` is invocable with these arguments and returns `deleted_t` (making the 2nd overload viable) then clearly `F` is invocable with these arguments (making the 1st overload viable). Both of these are function templates that are equivalently specialized (both take `Args&&...`{:.language-cpp} so neither is more specialized than the other). But our new one has a constraint (that `requires`{:.language-cpp} expression) and the old one does not, which is the easy way of being more constrained. Hence, it's the best match, which makes the whole overload deleted - as desired. We do not keep going to the next one like we did before.

You don't actually need concepts to implement this, I could have written two overloads and carefully ensured that they were mutually disjoint. But concepts makes it a lot easier.

Let's just add a nice helper to make the usage more readable:

```cpp
template <typename F>
struct delete_if {
    [[no_unique_address]] F f;
    
    constexpr delete_if(F f) : f(std::move(f)) { }
    
    template <typename... Args>
        requires std::invocable<F const&, Args...>
    auto operator()(Args&&...) -> deleted_t;
};
```

`delete_if` just wraps any callable and turns it into something that our `first_of` implementation will understand as wanting to propagate deletion. Its call operator doesn't need a function body because it's never actually going to be invoked anyway. The advantage of this helper (as you will see shortly) is that the callable doesn't need a body either.

Putting it altogether, we get the following complete and correct implementation of `ranges::begin`{:.language-cpp} with my new intended specification:

```cpp
namespace impl {
  template <typename T> void begin(T&&) = delete;
  template <typename T> void begin(std::initializer_list<T>&&) = delete;
  
  template <typename T>
  concept decays_to_iterator = std::input_or_output_iterator<
    std::decay_t<T>>;
    
  template <typename T>
  concept rvalue = std::is_rvalue_reference_v<T&&>;
  
  inline constexpr auto fn = first_of(
    // 1. reject rvalues
    delete_if([](rvalue auto&&){}),
    // 2. array case
    []<typename T, size_t N>(T (&arr)[N]) noexcept
    {
        return arr;
    },
    // 3. member case
    [](auto& rng)
        noexcept(noexcept(rng.begin()))
        requires decays_to_iterator<
            decltype(rng.begin())>
    {
        return rng.begin();
    },
    // 4. non-member case
    [](auto& rng)
        noexcept(noexcept(begin(rng)))
        requires decays_to_iterator<
            decltype(begin(rng))>
    {
        return begin(rng);
    }
  );
}

inline constexpr auto begin = impl::fn;
```

Personally, I really like reading this implementation because it's just linear, directly follows the spec, and is just correct by construction. You don't have to mess around with overload sets trying to ensure that one comes before the other. Or rather, you do - but in only a very narrow scope within the implementation of `first_of` itself. This solution is, in my opinion, just a lot easier to reason about than an approach that relies on having multiple `operator()`{:.language-cpp}s.