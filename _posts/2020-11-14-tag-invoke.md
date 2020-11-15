---
layout: post
title: "Why I hate tag_invoke"
category: c++
tags:
  - c++
  - c++20
pubdraft: yes
permalink: tag-invoke
---

With apologies to Lewis Baker, Eric Niebler, and Kirk Shoop.

C++ is a language that lauds itself on the ability to write good, efficient generic code. So it's a little strange that here we are in C++20 and yet have surprisingly little language support for proper customization. 

It's worth elaborating a bit on what I mean by "proper customization." There are a few facilities that I think of when I say this (in no particular order):

1. The ability to see clearly, in code, what the interface is that can (or needs to) be customized. 
1. The ability to provide default implementations that can be overridden, not just non-defaulted functions.
1. The ability to opt in _explicitly_ to the interface.
1. The inability to _incorrectly_ opt in to the interface (for instance, if the interface has a function that takes an `int`, you cannot opt in by accidentally taking an `unsigned int`).
1. The ability to easily invoke the customized implementation. Alternatively, the inability to accidentally invoke the base implementation. 
1. The ability to easily verify that a type implements an interface.

C++ has exactly one language feature that meets all of these criteria: virtual member functions. Given an interface, you can clearly see which functions are `virtual` or pure `virtual` (with the caveat that in some cases some `virtual` functions are inherited so you may have to look in multiple places). You can have functions that are pure virtual alongside functions that are virtual but have default implementations. Opting in must be explicit (both by way of having to inherit from the interface, and using `override` to annotate overrides - technically `override` isn't mandatory but compilers can enforce its usage via `-Wsuggest-override`).

If you attempt to override a function incorrectly, it's a compile error at the point of definition (as opposed to being an error at point of use, or worse not an error at all):

```cpp
struct B {
    virtual void f(int);
};

struct D : B {
    void f(unsigned int) override;  // error
};
```

Given a pointer to the interface, just invoking the function you want to invoke automatically does virtual dispatch per the language rules and invokes the most derived implementation. You don't have to do anything special. And lastly, checking if a type implements a particular interface is straightforward - just see if it inherits from the interface type. 

Using virtual functions for customization is easy to use and easy to understand precisely because the language gives us all this help.

Of course, virtual member functions have issues. None bigger than the fact that they are intrusive. You simply cannot opt types that you do not own into an abstract interface, with the fundamental types not being able to opt into any abstract interface at all. And even when the intrusiveness isn't a total non-starter, we have issues with performance overhead and the need for allocation.

## Parametric Polymorphism

There's another interesting aspect of using virtual functions for polymorphism that's worth bringing up. Let's pick one of the more familiar generic interfaces in C++: `iterator`. How would we implement `iterator` as an abstract base class? 

```cpp
struct input_iterator {
    // this one's fine
    virtual input_iterator& operator++() = 0;
    
    // no problem here either
    virtual bool operator==(input_iterator const&) const = 0;
    
    // .. but what about this one?
    virtual auto operator*() const -> ????;
};
```

Let's forget for the moment whether or not it is a good idea to even try to do this to begin with, what would `operator*` return here? There is no useful type we can put there that satisfies all `input_iterator`s - we might want to return `int&` for some iterators, `std::string const&` for others, `double*` for others, etc. 

What this example demonstrates is that `input_iterator` is a parameterized interface. And with virtual functions, the only we can provide those parameters is by adding template parameters. We take our interface and turn it into an interface template:

```cpp
template <typename R,
          typename V = remove_cvref_t<R>,
          typename D = ptrdiff_t>
struct input_iterator {
    using value_type = V;
    using reference = R;
    using difference_type = D;

    // okay now we can do this one
    virtual reference operator*() const;
};
```

But now we don't have an `input_iterator` interface, really. We can have an `input_iterator<int&>` interface and an `input_iterator<std::string const&>` one. But that's not... quite the idea we want to express. 

## Static Polymorphism

C++ has two strategies for static polymorphism which are non-intrusive:

* class template specialization
* free functions found by argument-dependent lookup (ADL)

Not only are both of these non-intrusive, but neither have any additional runtime overhead, nor do either typically require allocation. But how well do they actually do at customization?

### Class template specialization

We'll start with the former. 

Class template specialization is less commonly used than ADL-based free functions, but it's certainly a viable strategy. Of the more prominent recent libraries, `fmt::format` (and now `std::format`) is based on the user specializing the class template `formatter` for their types. The format library is, without reservation, a great library. So let's see how well its main customization point demonstrates the facilities I describe as desirable for customization.

First, can we tell from the code what the interface is? If we look at the [definition](https://github.com/fmtlib/fmt/blob/f8640d4050504ea15096c3861925956db40d436a/include/fmt/core.h#L629-L634) of the class template, we find:

```cpp
// A formatter for objects of type T.
template <typename T,
          typename Char = char,
          typename Enable = void>
struct formatter {
  // A deleted default constructor indicates
  // a disabled formatter.
  formatter() = delete;
};
```

This tells us nothing at all ❌. You can certainly tell from this definition that is intended to be specialized by _somebody_ (between the `Enable` template parameter and the fact that this class template is otherwise completely useless?) but you can't tell if it's intended to be specialized by the library author for the library's types or by the user for the user's types. 

In this case, there is no "default" formatter - so it makes sense that the primary template doesn't have any functionality. But the downside is, I have no idea what the functionality should be. 

Now, yes, I probably have to read the docs anyway to understand the nuance of the library, but it's still noteworthy that there is zero information in the code. This isn't indicative of bad code either, the language facility doesn't actually allow you to provide such.

The only real way to provide this information is with a concept. In this case, that concept could look like this. But the concept for this interface is actually [fairly difficult to express](http://eel.is/c++draft/formatter.requirements). 

Second, do we have the  ability to provide default implementations that can be overridden? ❌ Nope!

The `parse` function that the `formatter` needs to provide could have a meaningful default: allow only `"{}"` and parse it accordingly. But you can't actually provide default implementations using class template specialization as a customization mechanism &mdash; you have to override _the whole thing_. 

One way to improve this is to separate `parse` and `format`. Maybe instead of a single `formatter` customization class, we have a `format_parser` for `parse` and `formatter` for `format`. At least, this is an improvement in the very narrow sense that the user could specialize the two separately -- or only the latter. But I'm not sure it's an improvement in the broader sense of the API of the library. 

Third, do we have the ability to opt in explicitly to the interface? ✔️ Yep! In fact, explicit opt in is the only way to go here. Indeed, one of the reasons some people dislike class template specialization as a mechanism for customization is precisely because to opt-in you have to do so outside of your class. 

Fourth, is there any protection against implementing the interface incorrectly? ❌ Nope! If you do it sufficiently wrong, it just won't compile. Hopefully, the class author wrote a sufficiently good concept to verify that you implemented your specialization "well enough" so you get an understandable error message.

But worst case, your incorrect specialization might actually compile and just lead to bad behavior. Perhaps you're taking extra copies or forcing undesirable conversions? Very difficult to defend against this.

Fifth, can you easily invoke the customized implementation? ✔️ Yep! This isn't a problem with class template specialization. In this case, `formatter<T>::format` is the right function you want, and that's easy enough to spell. But do you get protection against invoking the wrong implementation? ❌ Nope! You could call `formatter<U>::format` just as easily, and if the arguments happen to line up... well... oops?

Although in this case, the customization point isn't really public-facing; it's only intended to be used internally by `std::format`. Other libraries will typically provide a separate, public-facing wrapper to avoid this problem. But it's something extra that needs to be provided by the class author. 

Sixth, can you easily verify that a type implements an interface? Arguably, ❌ nope! Not directly at all. You can check that a specialization exists, but that doesn't tell you anything about whether the specialization is correct. Compare this to the virtual function case, where checking if a `T*` is convertible to a `Base*` is sufficient for _all_ virtual-function-based polymorphism.

Here, it would be up to the class author to write a `concept` that checks that the user did everything right. But this also something extra that needs to be provided by the class author. 

So how'd we do? 2/6 maybe?

### ADL-based customization points

There has been innovation in this space over the years. We've used to have general guidelines about how to ensure the right thing happens. Then Ranges introduced to us Customization Point Objects. And now there is a discussion about a new model `tag_invoke`, whence the title of this blog post.

Ranges are probably the most familiar example of using ADL for customization points (after, I suppose, `<<` for iostreams, but as an operator, it's inherently less interesting). A type is a _range_ if it has a `begin` and `end` that yield an iterator and a sentinel for that iterator.

With pure ADL (ADL classic?), we would have code in a header somewhere (any of a dozen standard library headers brings it in) that looks like this:

```cpp
namespace std {
    template <typename C>
    auto begin(C& c) -> decltype(c.begin()) {
        return c.begin();
    }
    
    template <typename T, size_t N>
    auto begin(T(&a)[N]) -> T* {
        return a;
    }
    
    template <typename C>
    auto end(C& c) -> decltype(c.end()) {
        return c.end();
    }
    
    template <typename T, size_t N>
    auto end(T(&a)[N]) -> T* {
        return a + N;
    }    
}
```

Let's run through our six criteria real quick:

1. Can we see what the interface is in code? ❌ Nope! From the user's perspective, there's no difference between these function templates and anything else in the standard library.
1. Can you provide default implementations of functions? ✔️ Yep! The `begin`/`end` example here doesn't demonstrate this, but a different customization point would. `size(E)` can be defined as `end(E) - begin(E)` for all valid containers, while still allowing a user to override it. Similarly, `std::swap` has a default implementation that works fine for most types (if potentially less efficient than could be for some). So this part is fine.
1. Can we opt in explicitly? ❌ Nope! You certainly have to explicitly provide `begin` and `end` overloads for your type to be a range, that much is true. But nowhere in your implementation of those functions is there any kind of annotation that you can provide that indicates _why_ you are writing these functions. The opt-in is only implicit. For `begin`/`end`, sure, everybody knows what Ranges are &mdash; but for less universally known interfaces, some kind of indication of what you are doing could only help.
1. Is there protection against incorrect opt-in? ❌ Nope! What's stopping me from writing a `begin` for my type that returns `void`? Nothing. From the language's perspective, it's just another function (or function template) and those are certainly allowed to return `void`.
1. Can we easily invoke the customized implementation? ❌ Nope! Writing `begin(E)` doesn't work for a lot of containers, `std::begin(E)` doesn't work for others. A more dangerous example is `std::swap(E, F)`, which probably compiles and works fine for lots of times but is a subtle performance trap if the type provides a customized implementation and that customized implementation is _not_ an overload in namespace `std`. Instead, you have to write `using std::swap; swap(E, F)` which while "easy" to write as far as code goes, would not qualify as "easy" to always remember to do given that the wrong one works.
1. Can we easily verify the type implements an interface? ❌ I have to say no here. The "interface" doesn't even have a name in code, how would you check it? This isn't just me being pedantic - the only way to check this is to write a separate concept from the customization point. And this is kind of the point that I'm making - these are separate. 

Alright, 1/6. Can we do better?

### Customization Point Objects 

Customization Point Objects (CPOs) exist to solve several  of the above problems:

1. Provide an easy way to invoke the customized implementation. `ranges::swap(E, F)` just Does The Right Thing. This solves issue (5) above ✔️.
2. Provide a way to to verify that a type implements the interface correctly, addressing issue (4) above 😑. If a user provides a `begin` that returns `void`, `ranges::begin(E)` will fail at that point. This is not as early a failure as we get with virtual member functions, but it's at least earlier than we would otherwise get. But I'm not really open to giving a full check, since the way `ranges::begin` does this verification is that the author of `ranges::begin` has to manually write it.
3. Provide a name for the interface that makes it easier to verify, which addresses issue (6) 😑. As above, it is possible to provide, but it must be done manually.

They also lets you pass around the implementation into other algorithms, since now they're just objects, which is generally a big benefit but not really relevant to this specific discussion.

That gets us to 2/6 with another 2/6 manually. Progress!

The downside of Customization Point Objects, where customization is concerned, is that there's a lot of code you have to write to get there. But it also leads to those interface checks looking like this:

```cpp
template<class T>
  concept range =
    requires(T& t) {
      ranges::begin(t);
      ranges::end(t);
    };
```

This is the actual definition of the `range` concept in C++20. What actual criteria does this mean for `T`? Can we tell anything about the interface here? ❌ Nope. Could you tell by looking up the implementation of `ranges::begin` or `ranges::end`? ❌ Most people couldn't.

Let's take a different interface. Let's say instead of Ranges and Iterators, we wanted to do equality. We'll have two functions: `eq` and `ne`. `eq` must be customized to take two `T const&`s and return `bool`. `ne` can be customized, but doesn't have to be, and defaults to negating the result of `eq`. As a CPO, this would look something like this (where my library is `N`):

```cpp
namespace N::hidden {
  template <typename T>
  concept has_eq = requires (T const& v) {
    { eq(v, v) } -> std::same_as<bool>;
  };

  struct eq_fn {
    template <has_eq T>
    constexpr bool operator()(T const& x, T const& y) const {
      return eq(x, y);
    }
  };
  
  template <has_eq T>
  constexpr bool ne(T const& x, T const& y) {
    return not eq(x, y);
  }
  
  struct ne_fn {
    template <typename T>
      requires requires (T const& v) {
        { ne(v, v) } -> std::same_as<bool>;
      }
    constexpr bool operator()(T const& x, T const& y) const {
      return ne(x, y);
    }
  };
}

namespace N {
  inline namespace cpos {
    inline constexpr hidden::eq_fn eq{};
    inline constexpr hidden::ne_fn ne{};
  }
    
  template <typename T>
  concept equality_comparable =
    requires (std::remove_reference_t<T> const& t) {
      eq(t, t);
      ne(t, t);
    };
}
```

This is 42 lines of code.

It's worth reiterating that this is substantially better than raw ADL - if you just use `N::eq` and `N::ne` everywhere, you don't have to worry about issues like calling the wrong thing (perhaps some type has a more efficient inequality than simply negating equality? `N::ne` will do the right thing) or it being an invalid implementation (perhaps the user's implementation accidentally took references to non-const and mutated the arguments? This wouldn't compile). But this is _not_ easy to write, and for such a straightforward interface, you can't really tell what it is anyway without some serious study.

CPOs improve upon just raw ADL names by allowing you to verify more things. But they come at some cost. While they provide the user a way to ensure they call the correct implementation and provide checking for the user that they implemented the customization point correctly (to some extent), that comes with a cost: somebody had to write all of that by hand, and it's not necessarily cheap to compile either. Even though we're addressing more of the customization facilities that I'm claiming we want, these are much harder and time-consuming interfaces to write... that nevertheless are quite opaque. 

### `tag_invoke`

The `tag_invoke` paper, [P1895](https://wg21.link/p1895), lays out two issues with Customization Point Objects (more broadly ADL-based customization points at large):

1. ADL requires globally reserving the identifier. You can't have two different libraries using `begin` as a customization point, really. Ranges claimed it decades ago. 
2. ADL can't allow writing wrapper types that are transparent to customization.

Now, the second issue is one of those things that actually only happens in an especially narrow set of circumstances, and not one that I've personally ever run into (the paper cites executors and properties as examples, which is a fairly massive thread of discussion that I have not followed at all).

So, instead I'll focus on the first point. This is an unequivocally real and serious issue. C++, unlike C, has namespaces, and we'd like to be able to take advantage that when it comes to customization. But ADL, very much by design, isn't bound by namespace. With virtual member functions, there are no issues with having `libA::Interface` and `libB::Interface` coexist. Likewise with class template specializations - specializing one name in one namespace has nothing to do with specializing a similarly-spelled name in a different namespace. But if `libA` and `libB` decide that they both want ADL customization points named `eq`? You better hope their arguments are sufficiently distinct or you simply cannot use both libraries.

The goal of `tag_invoke` is to instead globally reserve a single name: `tag_invoke`. Not likely to have been used much before the introduction of this paper. 

The implementation of `eq` interface above in the `tag_invoke` model would look as follows:

```cpp
namespace N {
  struct eq_fn {
    template <typename T>
      requires std::same_as<
        std::tag_invoke_result_t<eq_fn, T const&, T const&>,
        bool>
    constexpr bool operator()(T const& x, T const& y) {
      return std::tag_invoke(*this, x, y);
    }
  };
  
  inline constexpr eq_fn eq{};
  
  struct ne_fn {
    template <typename T>
      requires std::invocable<eq_fn, T const&, T const&>
    friend constexpr bool tag_invoke(
        ne_fn, T const& x, T const& y) {
      return not eq(x, y);
    }
  
    template <typename T>
      requires std::same_as<
        std::tag_invoke_result_t<ne_fn, T const&, T const&>,
        bool>
    constexpr bool operator()(T const& x, T const& y) {
      return std::tag_invoke(*this, x, y);
    }
  };
  
  inline constexpr ne_fn ne{};
  
  template <typename T>
  concept equality_comparable =
    requires (std::remove_reference_t<T> const& t) {
      eq(t, t);
      ne(t, t);
    };  
}
```

This is... 39 lines of code. Granted, some of the above is spaced for the blog to avoid scroll-bars, so I think in real code this would probably be shorter than the CPO solution by a larger amount than 3 lines.

To what extent does this `tag_invoke`-based implementation of `eq` and `ne` address the customization facilities that regular CPOs fall short on? It does help: we can now explicit opt into the interface (indeed, the only way to opt-in is explicit) ✔️!

But the above is harder to write for the library author (I am unconvinced by the claims that this is easier or simpler) and it is harder to understand the interface from looking at the code (before, the objects clearly invoked `eq` and `ne`, respectively, that is no longer the case). When users opt-in for their own types, the opt-in is improved by being explicit but takes some getting used to:

```cpp
struct Widget {
  int i;
  
  // with CPO
  constexpr friend bool eq(Widget a, Widget b) {
    return a.i == b.i;
  }
  
  // with tag_invoke
  constexpr friend bool tag_invoke(std::tag_t<N::eq>,
                                   Widget a, Widget b) {
    return a.i == b.i;
  }
};

// if we did this as a class template to specialize
template <>
struct N::Eq<Widget> {
    static constexpr bool eq(Widget a, Widget b) {
        return a.i == b.i;
    }
    
    // have no mechanism for providing a default
    // so it's either this or have some base class
    static constexpr bool ne(Widget a, Widget b) {
        return not eq(a, b);
    }
};
```

That's okay, we can get used to this right? It's C++.

If you look at the scoreboard, `tag_invoke` seems to meet 3 of the 6 criteria I set out initially: you can provide default implementations, you can opt-in explicitly, and you can easily invoke the correct implementation. And then 2 more of the 6 criteria can be met if the library author does a good job: the ability to do _some_ checking that the interface was correctly implemented (can't catch everything, but can catch something) and the ability to verify that a type implements an interface (this isn't automatic because if you have multiple customization points, as in `eq`/`ne` above, there is no broader grouping of them).

## This isn't better enough

If `tag_invoke` is improving on CPOs (and it is, even when I measure by criteria that are not related to the problems the authors set out to solve), why do I claim, as I do in the title of this post, the I hate `tag_invoke`?

Because this is how you implement the `eq`/`ne` interface in Rust, which calls this `PartialEq`:

```rust
trait PartialEq {
    fn eq(&self, rhs: &Self) -> bool;
    
    fn ne(&self, rhs: &Self) -> bool {
        !self.eq(rhs)
    }
}
```

This is 7 lines of code.

And this trivial implementation, which you probably understand even if you don't know Rust, meets my six criteria easily. And unlike CPOs and `tag_invoke`, where the extent of the ability to protect the user from faulty implementations or provide them with interface checks is dependent on the class author writing them correctly, here these checks are handled by and provided by the language. As a result, the checks are more robust, and the interface author doesn't have to do anything. 

Moreover, it even meets one of `tag_invoke`'s stated criteria: it does not globally reserve names. Though it does not meet the other: you cannot transparently implement and pass-through a trait that you do not know about. 

Ultimately, I want us to aspire to more than replacing one set of library machinery that solves a subset of the problem with a different set of library machinery that solves a larger subset of the problem... where neither of set of library machinery actually gives you insight into what the interface is to begin with.

We already have one customization facility in the language: virtual member functions. I think it's high time we added another.

### Can `tag_invoke` help me write an iterator?

Let's get back to the iterator example. I brought up earlier in the post that you can't really do a good job of implementing iterator using virtual functions due to the need to provide parameters. Can we do better with any of the ADL-based facilities?

Nope.

All the ADL-based facilities are built around being able to write a non-member function. These are all inherently stateless customization points. They don't really help you build up a class with member functions. The best you can do there, as of today, is to use Zach Laine's [Boost.STLInterfaces](https://www.youtube.com/watch?v=Sv_hqkjra2Y) library.

One of the nice features of the library is that for random access iterators, you really only have to implement `operator*()`, `operator+=(ptrdiff_t)`, and `operator-(iterator)`. And the library for you will implement all the iterator advancing functions: `operator++()`, `operator++(int)`, `operator--()`, `operator--(int)`, `operator+(ptrdiff_t)`, `operator-(ptrdiff_t)`, `operator+=(ptrdiff_t)`, and `operator-=(ptrdiff_t)`. Better than average chance I missed one. How would we provide default implementations for those using Customization Point Objects or `tag_invoke`? You can't - there's nowhere for me to put an `operator++()` (or any of the others) such that `++it` for your iterator will definitely find it. 

That is, if your customization interface is just a function or two or three, `tag_invoke` works. But if you want to write a _type_, especially a type that uses operators, then you're kind of on your own. And if you want to write a type with a lot of defaultable implementations, then you better hope you know a Zach who can help you avoid the boilerplate.

What this means it that we have different customization mechanisms for every kind of customization that needs to be done:

- handful of free functions? `tag_invoke` is the best we've got.
- need to produce _type_ or constant (e.g. `tuple_element` and `tuple_size`) rather than some kind of functionality? Use class template specialization (although it's technically possible to implement these in terms of `tag_invoke` as well).
- need to produce a whole type that implements an interface? Make a CRTP class and use inheritance. 

It's already a big ask to have a language feature that solves the customization problem for free functions in a superior way to `tag_invoke`. But these situations really aren't as different as the solutions to them make it seem. Would it be too much to ask to have a uniform customization mechanism for all three kinds of problem?