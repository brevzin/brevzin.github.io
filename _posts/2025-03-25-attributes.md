---
layout: post
title: "On the Ignorability of Attributes"
category: c++
tags:
 - c++
 - c++26
---

I was reading through the latest mailing, and a sentence caught my eye in [P3661 (“Attributes, annotations, labels”)](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2025/p3661r0.html), emphasis mine:

> **Attributes turned out to be unsuitable** for the role of "small features", "small modifications to bigger features" or *annotations* from other languages. The need for a new kind of **non-ignorable annotation** pops up time and again in different places. Given that the addition of this new kind of entity seems inevitable, we recommend that only one syntax is used for all the cases that need it.

Attributes turned out to be unsuitable for solving problems because they are ignorable. I found this a very frustrating introduction to read. Because, on the one hand, it’s true — C++ attributes are, today, completely unsuitable for solving any problem. How did we actually get into this situation? How did we decide that attributes must be useless?

A couple years ago, we had [P2552 (“On the ignorability of standard attributes”)](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2023/p2552r3.pdf). However, this paper does not actually argue that attributes *should* be ignorable. Or even suggest the existence of such an argument. It simply has this to say in its abstract:
> There is a general notion in C++ that standard attributes should be *ignorable*.

And then a little while later we get:

> On the other hand, it is uncontroversial that attributes are meant to be *semantically* ignorable.

The rest of the (fairly long) paper proceeds to attempt to define in very specific terms what exactly ignorable means.

But I’m here to argue something else entirely. It should be *extremely* controversial that attributes are meant to be semantically ignorable — for any possible definition of semantically or ignorable. That decision has harmed, and continues to harm, language evolution. We’ve made worse decisions for language features in the past, we’re making worse decisions for language features in the present, and we have to spend a tremendous amount of time discussing and solving self-imposed problems that attributes were meant to solve — simply because we have decided that we want to make attributes as useless as possible.

## The introduction of `[[attributes]]`

The last revision of the proposal for C++11 was [N2761 (“Towards support for attributes in C++ (Revision 6)”](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2008/n2761.pdf).

> How great is it that we changed the paper numbering system to separate number from revision — N2761 obviously was a revision of N2751 which was a revision of N2553. You just… had to know?
{:.prompt-info}


That final paper started with this very insightful and future-looking introduction:
> The idea is to be able to annotate some entities in C++ with additional information. Currently, there is no means to do that short of inventing a new keyword and augmenting the grammar accordingly, thereby reserving yet another name of the user's namespace.

Before this proposal, implementors had already recognized the need for adding more information to entitites. GCC had `__attribute__((thing))` and MSVC had `__declspec(thing)`. The standard attribute feature provided two significant benefits:

1. Nicer syntax. `[[thing]]` is just a lot nicer to read than `__attribute__((thing))`, where we had 17 characters of overhead instead of just 4.
2. Precise rules around appertainment. Where do you put an an attribute if you want it to apply to a type? A variable? The C++11 rules are very clear about this, and GCC in particular was kind of all over the place. The placement was bespoke for each attribute.

Now maybe a slightly different syntax could have been better, like `[#[thing]]`, which wouldn’t clash with nested structured bindings, but it’s hard to hold that against the design. But regardless, these are two very significant benefits! We got a lot of clarity, and suddenly got a language feature to allow annotating entities with additional information that — and I really want to stress this — avoids entirely the problem of inventing new keywords and having to deal with grammar. The issue here isn’t just dealing with grammar and coming up with suitable keywords, it’s also that dealing with grammar completely subverts the benefit that we get with precise rules around appertainment. I’ll talk more about this in a bit.

> Note, by the way, that in this paper, `align` was an attribute:
> ```cpp
> struct [[align(64)]] C { };
> ```
>
> That was changed in [N3190 (“C and C++ Alignment Compatibility*)](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2010/n3190.htm) back to a keyword — but not > because of anything having to do with ignoring attributes, it was simply due to C compatibility. Note that this paper does not make any mention of ignoring > attributes. It’s that C didn’t have attributes yet, and C1x was pursuing `_Align(...)`  so to unify the two languages, we ended up with `alignas(...)` in C++11 and > `_Alignas(...)` in C11 (C23 later adds `alignas)`.
{:.prompt-info}

That paper also had some guidance on when to use an attribute:

> So what should be an attribute and what should be part of the language.
>
> It was agreed that it would be something that helps but **can be ignorable with little serious side-effects**.

and

> There was general agreement that attributes should not affect the type system, and **not change the meaning of a program regardless of whether the attribute is there or not**.

And yet... examples presented for what makes a good attribute were `align(...)` and `thread_local`. Those very clearly affect the meaning of a program.

Nevertheless, the paper did provide what I still consider to be useful guidance for when to not use an attribute:

> Some guidance for when not to use an attribute and use/reuse a keyword
>
> * The feature is used in expressions as opposed to declarations.
> * The feature is of use to a broad audience.
> * The feature is a central part of the declaration that significantly affects its requirements/semantics (e.g., `constexpr`).
> * The feature modifies the type system and/or overload resolution in a significant way (e.g., rvalue references). (However, something like near and far pointers
should probably still be handled by attributes, although those do affect the type system.)
> * The feature is used everywhere on every instance of class, or statements

Now while we can argue about what makes an audience "broad" — I do think this particular list is a lot more useful and interesting than talking about ignoring the attribute entirely. I would go so far as to suggest that neither `align(...)` nor `thread_local` meet any of these criteria, so I agree with the paper in this regard — they would have made for good attributes and did not need to become keywords.


## The demise of `[[override]]`

After the introduction of a standardized facility to "annotate some entitites [...] with additional information," there were many proposals to add such annotations to the standard. Because, after all, these is quite a lot of interesting information that you could add to entities in a way that is useful to programmers!

One such example was [N2928 ("Explicit Virtual Overrides")](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2009/n2928.htm), which introduced the `[[override]]` attribute (yes, attribute). This solves two problems that are somewhat mirrors of each other:

* I want to declare my own function, that _accidentally_ overrides a base class function
* I want to override a base class function _on purpose_, but I do it incorrectly (e.g. I get the name, parameters, etc., slightly wrong).

`[[override]]` is a great solution to that problem. Its usage completely solves the second problem and, coupled with compilers' additions of `-Wsuggest-override`, diagnosing its absence completely solves the first. I was very happy when gcc 5.1 added that warning, as I'd been [looking for a solution to this problem](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2009/n2928.htm).

`[[override]]` also very clearly meets all the criteria laid out in the original attributes paper. `[[final]]` was even presented as an example of a good attribute (as well as a potential `[[not_hiding]]`, which is kind of the opposite of `[[override]]`).

Now, sometime later, `[[override]]` was changed instead from an attribute to a contextual keyword. You can find the argument for that in [N3151 ("Keywords for override control")](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2010/n3151.html). That paper says this:

> Several experts have lamented the solution, saying that it uses attributes for semantic effects and that the language shouldn't use such semantic effects itself as that sets a bad example. Furthermore many people consider the attributes ugly.

That... is not an argument. It is not close to an argument. It is about as close to being an argument as I am to being an Olympic swimmer. Sure, maybe the contours are vaguely present? But I don't particularly care that "several experts" don't like this or that "many people" consider this ugly.

The consequence is that instead of:

```cpp
struct B {
    virtual void f() = 0;
};

struct D : B {
    [[override]] void f();    // ok
    [[override]] void f(int); // error
};
```

we ended up with:

```cpp
struct D : B {
    void f() override;    // ok
    void f(int) override; // error
};
```

And this is... worse. It's worse for several reasons, which are somewhat recurring themes.

First, it introduces additional inconsistency that must be learned. Where does additional information on a function go? It depends. `[[noreturn]]` goes at the front, `override` goes at the end. But where at the end, where in relation to the other pieces of information? In particular, which of these is correct:

```cpp
void f() const override;          // #1
void f() override const;          // #2
auto f() const override -> void;  // #3
auto f() override const -> void;  // #4
auto f() const -> void override;  // #5
```

In case you were wondering, the answer is `#1` and `#5`. Can you tell me where `noexcept` goes?

> I asked two people, who are very knowledgeable C++ programmers. They gave me two, different, incorrect answers.
{:.prompt-info}

Now, it's not like you don't have to memorize the location of attributes. You do. But you only have to memorize the location of attributes one time. You have to memorize the location of every new keyword we add, independently.

Second, it requires a discussion about what token to use. Do we use a keyword or a contextual keyword? Are there ambiguous parses? How often are these words used? Does it have to be an ugly keyword? There were papers and discussions that had to happen about this.

This was one of the motivations of attributes — to avoid these problems completely.

Now, as a result, we end up in a situation where this is valid:

```cpp
struct base {
    virtual auto override() const -> void;
};

struct final final : base {
    auto override() const -> void override;
};
```

Now, probably nobody is going to write this code outside of C++ quizzes, so it's not a exactly anti-motivating in of itself. But I have actually used `override` and `final` as identifiers before, or at least tried to until they got syntax-colored. And we intentionally made these things contextual keywords instead of keywords because anonymous people somewhere didn't like... something?


## Harming Past Language Evolution

In C\++11 we ended up in a state where `[[override]]` and `[[final]]` could have been attributes, but instead were contextual keywords. But then `[[deprecated]]` got introduced in C++14 and `[[nodiscard]]` in C\++17. So now we're in this state where if you want to introduce a new facility whose purpose is to issue a diagnostic on otherwise valid code, you either:

* make it an attribute (`[[deprecated]]` and `[[nodiscard]]`), or
* make it a contextual keyword (`override` and `final`).

That's not a particularly solid foundation on which to build.

In the C\++20 timeframe, we had another proposal to add information onto a declaration of an entity whose entire purpose was to diagnose otherwise valid code: [P1143R0 ("Adding the `[[constinit]]` attribute")](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1143r0.md). This paper's goal was to address the Static Initialization Order Fiasco by diagnosing certain static storage variables with non-constant initializers, based on implementation experience with clang:

```cpp
struct T {
      constexpr T(int) { }
    ~T(); // non-trivial
};

 // OK
[[clang::require_constant_initialization]] T x = {42};

// error: variable does not have constant initializer
[[clang::require_constant_initialization]] T y = 42;
```

Now, the attribute there is a mouthful — but I don't think that actually matters. There aren't many situations where it is important that a static storage duration variable has constant initialization, and it seems valuable to have a clear annotation to cover that case. `[[require_constant_initialization]]` is very clear. This also doesn't meet any of the originally laid out criteria for when to use a keyword. Regardless of your definition of "broad audience," this ain't it.

Except that, again, for reasons, the proposal to add an attribute (which was abbreviated to `[[constinit]]`) changed to instead propose a *keyword*. From [R1](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2019/p1143r1.md) of that paper:

> in r0 of this paper `constinit` was proposed as an attribute. When this idea was presented, there was general concencious that this feature would be better suited as a keyword. First, `constinit` enforces correctness and **if compilers were allowed to ignore it as they can attributes**, it would allow "ill-formed" programs to compile. Second, there was some discussion about the behavior of `[[constinit]]` being out-of-scope for attributes (I don't believe this to be the case).

This is a very bizarre argument. Now, we had already at this point had two attributes (`[[nodiscard]]` and `[[deprecated]]`) that already existed for exactly the same reason. A static initialization order bug is bad. But discarding a result that it was important to hold onto could also be bad. If you write `lock_guard(mtx);` instead of `auto _ = lock_guard(mtx);`, you're introducing a data race. If you had an unintentional `override`, you have a function which could suddenly be invoked when you didn't expect or desire it. Is the decision purely based on who prioritizes which level of badness?

So in C++20, purely considering language features whose purpose is to introduce diagnostics on otherwise-valid code, we now have this trichotomy:

* attribute (`[[deprecated]]` and `[[nodiscard]]`)
* contextual keyword (`override` and `final`)
* keyword (`constinit`)

This could have simply been `[[deprecated]]`, `[[nodiscard]]`, `[[override]]`, `[[final]]`, and `[[require_constant_initialization]]`. Nice and uniform.

## Who does ignoring attributes help?

At this point we've seen allusions in multiple papers to this idea that compilers are allowed to ignore attributes. The question I have always had is: why would any C++ programmer _want_ compilers to be able to ignore attributes?

The strongest answer I know of to that question is as follows. Let's say I'm writing a library, and I want to indicate that the return of some function shouldn't be discarded:

```cpp
[[nodiscard]] auto f(int) -> int;
```

I want this library to work on compilers that don't support `[[nodiscard]]` yet. Indeed, I want this to work on C++14 in general. And in those cases... well, there's nothing I can actually _do_ to trigger a discarding warning anyway. So if those compilers simply ignored the attribute, I could use the nice, pretty attribute syntax instead of having to do this:

```cpp
#if __has_cpp_attribute(nodiscard)
# define LIB_NODISCARD [[nodiscard]]
#else
# define LIB_NODISCARD
#endif
```

so that later I could do this:
```cpp
LIB_NODISCARD auto f(int) -> int;
```

It's certainly nicer to read the former than the latter. And this, superficially, seems like a good argument.

However, consider:

```cpp
[[nodiscard]] auto f(int) -> int;
[[nodicsard]] auto g(int) -> int;
```

Sure, my C\++14 compiler will happily ignore these attributes because it doesn't know them. But while my conforming C\++17 and C\++20 compiler will warn on discarding the result on `f(42)` but it still won't warn on discarding the result of `g(17)`.

Why? Because I misspelled the attribute. And turns out there's not actually any difference between "the compiler ignores my attribute because it is not implemented yet in this release" and "the compiler ignores my attribute because I misspelled it and thus it will not be implemented in any release, ever."

Allowing the compiler to ignore attributes means that the compiler will completely ignore my bug, and that to me is unacceptable.

If I wanted the compiler to ignore code that I wrote, I already have perfectly good mechanisms available to me. I could write a comment. I could use the preprocessor to wrap some code in `#if`. I see no reason why we need to pretend that C++11 introduced two new digraphs into the language.

> `[[` for `/*` and `]]` for `*/`. But only sometimes.

It just strikes me as incredibly user-hostile to ignore user code like this. I often see discussions around optimization where people anthromorphize the compiler as being a hostile entity that deliberately miscompiles user code when they mess up — when in reality it was the result of a complex interplay of optimizations, assumptions, and undefined behavior. But ignoring actual code that users wrote because attributes? That's just objectively hostile.

Thankfully, compilers do not *actually* behave like this. If you write this:

```cpp
[[nodicsard]] auto g(int) -> int;
```

Both gcc and clang, even without `-Wall`, diagnose this very clearly as an unknown attribute.  MSVC warns here as well, but it requires `/W3`. Now, that is a diagnostic you can ignore if you choose to (it is `-Wattributes` on gcc and `-Wunknown-attributes` on clang). But if you *choose* to ignore it, that is a choice you are making for your own code — and that sort of thing is perfectly fine. That is very different from the compiler choosing to do it.

Besides, there seems like there should be a better way to allow users to use not-yet-implemented attributes in a way that is not simply ignoring user code. This situation really only applies to certain attributes anyway (and I'll talk about another one such shortly), but perhaps a better solution would be to allow code to explicitly declare that it will use certain attributes:

```cpp
#if not __has_cpp_attribute(nodiscard)
// or something
#  pragma GCC attribute nodiscard
#endif

// on a new compiler, this is just recognized
// on an old compiler, we explicitly declared it
[[nodiscard]] auto g(int) -> int;
```

This explicit declaration is significantly better than silently ignoring unknown attributes. Because we don't actually _want_ to ignore them. Either the implementation knows about them already, or there are _specific_ ones we want to inform the implementation about. But there's no value to silently dropping what's in `[[...]]`.

Moreover, it's not like adding a `nodiscard` keyword would've really done anything to help this problem anyway?

### Addressing the unique case of `[[no_unique_address]]`

Now, the elephant in the room is `[[no_unique_address]]`. Because while ignoring `[[nodiscard]]` or `[[deprecated]]` is bad, the consequence of that ignoring is simply not getting desired diagnostics — and a future compiler release will alleviate that problem.

But ignoring `[[no_unique_address]]` and recognizing it in a future release is a lot worse than that. Because that's an ABI break. The Microsoft blog [called this out](https://devblogs.microsoft.com/cppblog/msvc-cpp20-and-the-std-cpp20-switch/):

> Implementation of C\++20 [[no_unique_address]] included a couple of additional challenges due to the ABI-breaking impact (changing object layout) of applying this optimization. **This is problematic due to the MSVC compiler ignoring attributes that are not known**, as allowed by the standard, resulting in scenarios where MSVC ABI compatibility guarantees would be broken for standard C++ code:
>
> * Compiling the same header/source under /std:c++17 and /std:c++20 would result in link-time incompatibilities due to object layout differences resulting in ODR violations.
> * Linking static libraries built with an older version of the MSVC compiler (VS 2015 through VS 2019 v16.8), within the v14x ABI-compatible family, would result in ODR violations and break our compatibility guarantees.

So now libraries that want to work with Microsoft have to use `[[msvc::no_unique_address]]` instead. That is, the nominal benefit of ignoring attributes was that we could have just written `[[no_unique_address]]` — but instead we have to write *even more* preprocessor checks.

This example is sometimes presented as an argument that `[[no_unique_address]]` shouldn't have been an attribute. But really it's a great example that attributes should never have been ignorable.

## Harming Present Language Evolution

At the Hagenberg meeting, one of the new language/library features adopted for C++26 was trivial relocation ([P2786R13](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2025/p2786r13.html)). The relevant part of this facility, as far as this blog post is concerned, is the shape and spelling of the facility. It introduces two contextual keywords that go... here:

```cpp
template <class T>
struct unique_ptr
    trivially_relocatable_if_eligible
    replaceable_if_eligible
{
    // ...
};
```

Now, I think this is already bad because other class annotations go in a different spot — `[[nodiscard]]` and `alignas` (while not an attribute anymore) go between `struct` and the class name. Technically `final` also goes after the class name, but that one is very rarely used.

But where it gets worse is that this feature should have an extra piece of functionality that it doesn't — primarily because the opt-in is a contextual keyword rather than an attribute.

The paper presents motivation for, and an example implementation of, a class template that wants to conditionally disable trivial relocation. Were this an attribute, that would be trivial:

```cpp
template <class T>
class
    [[trivially_relocatable_if_eligible(std::is_trivially_relocatable_v<T>)]]
    optional
{
    alignas(T) std::byte buffer_[sizeof(T)];
    bool engaged_ = false;
    // ...
};
```

Yes, the above is... very verbose. But the offered solution in the paper is that we should instead write this:

```cpp
template <bool TriviallyRelocatable>
struct ConditionalProperties { };

template <>
struct ConditionalProperties<false> {
    ~ConditionalProperties() { }
};

template <class T>
class optional trivially_relocatable_if_eligible {
    alignas(T) std::byte buffer_[sizeof(T)];
    union {
        bool engaged_ = false;
        ConditionalProperties<std::is_trivially_relocatable_v<T>> _;
    };
    // ...
};
```

Now, if there is one unifying aspect to all of the proposals I have ever written for C++, it is the desire to be able to directly express intent. In the C++20 timeframe, I even pushed for _two_ different language features that were _specifically_ about being able to directly express that a type conditionally has some property:

* [P0892 ("`explicit(bool)`")](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0892r2.html) — to mark a constructor as being conditionally explicit
* [P0848 ("Conditionally Trivial Special Member Functions")](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2019/p0848r3.html) — to be able to mark a templated class as being conditionally trivially copyable, etc.

So you can imagine my dismay when seeing a brand new C++26 feature that has exactly this same kind of problem.

The reason that the proposal doesn't outright support a condition is because of an ambiguous parse here:

```cpp
// this looks like a function named "trivially_relocatable_if_eligible"
// which takes a Bar and returns a Foo
struct Foo trivially_relocatable_if_eligible(Bar) { /* ... */
```

Now, no matter what, we should just solve this problem. Since `trivially_relocatable_if_eligible` is a contextual keyword, we can just add a contextual parse rule. Or make it a full keyword.

But... this is an _entirely_ self-imposed problem. If we had `[[trivially_relocatable_if_eligible]]`, this would never have needed to even be a discussion. It's useful to take a condition, so we'd add a condition, and there's obviously no ambiguity to deal with.

And it's an entirely self-inflicted burden that we don't even derive benefit from. Just more work.

## Harming Future Language Evolution

What about other language features that we might some day consider adopting in the future? People often talk about how we should be standardizing existing practice, so let's take a look at existing attributes and what we would have to do about them if we chose to adopt them.

* `[[gnu::packed]]` is kind of a double-edged sword that I used to use a lot to write types for networking and serialization. And since it affects the alignment of every member, is obviously a non-starter in our current model of "attributes are not allowed to do anything". That would have to be a keyword. Good luck coming up with one, or where it should go.
* `[[clang::lifetimebound]]` is an attempt to diagnose more lifetime issues in clang. It's far from a complete solution, and there's only a fairly narrow set of problems that it catches. However, that is still a lot of lifetime bugs that could be caught with an attribute that cannot be diagnosed at all today! How would we go about standardizing this one? I suppose we're going to have a very, very long discussion about whether a `[[lifetimebound]]` violation rises to the level of a keyword, just a contextual keyword, or just an attribute. After all, we have some of each. How would you even decide which one to pick? Vibes?
* `[[gnu::constructor]]` is a way to decorate a function as being invoked before `main` is executed, and even can take a `priority` parameter to help order static initialization logic across multiple translation units. It's a very useful way to directly express both intent and ordering. Obviously, changing whether a function is invoked or not is a pretty big semantic change, so I guess this is also not an attribute and we'd need to come up with some spelling for it.

I'm sure there's plenty of other good examples of very useful implementation-defined attributes that solve real problems that users have, by adding semantics to programs that attributes aren't allowed to have.

Another interesting one is `[[noreturn]]`. That's a C++11 attribute. But currently other parts of the language don't take advantage of it. Should we?

```cpp
int x = cond ? std::abort() : 42;
```

Conceptually, this is perfectly valid code — and if we replaced `std::abort()` with a `throw` it would even compile. Can we extend the conditional operator to recognize `[[noreturn]]`?

The answer right now is that it doesn't even matter if we should, because we've simply decided we're not allowed to.

## Non-Ignorable Attributes

We're in this very strange state where we have a perfectly adequate facility to allow us to add more information to entities in a way that avoids dealing with grammar issues, avoids clashing names, and avoids putting more cognitive burden on users to have to remember increasingly complicated declaration orders.

But we also decided that this facility is not allowed to do anything. So instead, we have people pursuing a new kind of _non-ignorable_ attribute. While at the same time spending lots of time solving problems that we invented for ourselves.

None of this is helping anybody. I think it's time to stop the bleeding.

Or, perhaps I should put it differently.

> Several experts have lamented the solution, saying that introducing new keywords for every small feature itself sets a bad example. Furthermore many people consider all of these free-floating words ugly.