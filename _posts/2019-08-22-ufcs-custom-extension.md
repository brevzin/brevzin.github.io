---
layout: post
title: "UFCS: Customization and Extension"
category: c++
series: ufcs
tags:
 - c++
 - c++20
--- 

In my previous post on the topic, I went through all the proposals we've had that were in the general space of unified function call syntax. That is, anything in which member function syntax might find a non-member function or non-member syntax might find a member function - with multiple sets of rules to disambiguate in case of multiple candidates. In this post, I wanted to go over how well these proposals solve the problems they set out to solve. For simplicity, I'm going to pick just one of the candidate set options, CS2 (`x.f(y)`{:.language-cpp} can find `f(x, y)`{:.language-cpp}), and I am going to completely ignore the question of overload resolution. I'm deliberately taking the simplest possible version of the problem.

There are really two main kinds of problems that UFCS set out to solve. They're closely related but they're not the same. The way I would describe these two problems are _customization_ and _extension_. The difference between the two boils down to who knows what:

- customization: I know there is some `f` that I can call on this unknown type `x`, but I don't know whether that's `x.f()`{:.language-cpp} or `f(x)`{:.language-cpp}. How do I call the right one?
- extension: I know which `f` I want to call, but I want to call it like `x.f()`{:.language-cpp} and not like `f(x)`{:.language-cpp}. How do I get the nice syntax (both from an auto-complete perspective and a reading left-to-right perspective)?

I'll go over both in detail.

## Customization

The most familiar example of customization to everyone is ranges. It's one that even has language support: the range-based for statement. It's one whose language support even comes with a unified function call syntax! The loop:

```cpp
for (auto const& e : elems) { /* ... */ }
```

will work regardless of whether `elems` has a member `begin` or a non-member `begin`. Either way works. 

Let's go over a simple example. I'm sick of having to manually pass in an iterator pair into `std::find`{:.language-cpp} and would like to write a version of that algorithm that takes a range as its first argument (C++20 will include a `std::ranges::find`{:.language-cpp} for this purpose). One of the motivations of UFCS was that I could write it this way:

```cpp
template <typename Range, typename Value>
auto find(Range& r, Value const& value)
{
    auto first = r.begin();
    auto last = r.end();
    for (; first != last; ++first) {
        if (*first == value) {
            return first;
        }
    }
    return last;
}
```

That is, we have some type `Range`. We expect that it somehow adheres to the language range concept in that it has both a `begin()`{:.language-cpp} and `end()`{:.language-cpp} function associated with it -- but we don't know if that association is as a member function or a non-member function. UFCS proposes that rather than having to know which is the correct syntax (or, more accurately, doing the necessary template metaprogramming to find out), we write this up as a language rule. 

With C++20 concepts, we can actually write this in-line - but this isn't something we would actually want people to do regularly (especially with such a common concept as range):

```cpp
auto first = [&]{
    // if we can actually call r.begin()...
    if constexpr (requires { r.begin(); }) {
        // ... then do that
        return r.begin();
    } else {
        // ... otherwise use the non-member
        return begin(r);
    }
}();
```

Writing `r.begin()`{:.language-cpp} is surely a lot easier on the eyes, and fingers, and compiler, than writing that immediately-invoked lambda. What's not to love? 

But here's the question: is this actually sufficient? That is, let's say we did adopt something like this language rule (pick the candidate set and overload resolution rules of your choice). Would that solve this problem?

I don't think it does. Because there are actually more cases than I've discussed so far where ranges are concerned. 

In the above code, we're trying one of two options: `r.begin()`{:.language-cpp} and `begin(r)`{:.language-cpp}. The former is going to find the member functions, no wrinkles there. The latter is going to find all `begin()`{:.language-cpp}s that are either in scope or can be found using argument-dependent lookup (ADL). That's a lot of functions, but there's still something missing. The problem is arrays.

If I have a `lib::Widget[10]`{:.language-cpp}, that's something I can iterate over and it's something I'd want to be able to use in my `find()`{:.language-cpp}. This doesn't have a member `begin()`{:.language-cpp} (arrays don't have any member functions). Which non-member `begin()`{:.language-cpp} would work? Our associated namespace here is `lib`{:.language-cpp}, but you can't expect somebody to write a `begin()`{:.language-cpp} in every namespace in which they declare types that somebody, somewhere, might stick in an array. That's absurd. And even if you had that expectation, it would break once I tried to use a type as esoteric as... `int[10]`{:.language-cpp}. `int`{:.language-cpp} has no associated namespaces.

In order for this to work at all, there have to be functions that can be found with unqualified lookup to handle the array cases:

```cpp
template <typename T, size_t N>
auto begin(T (&arr)[N]) -> T* { return arr; }
template <typename T, size_t N>
auto end(T (&arr)[N])   -> T* { return arr+N; }

template <typename Range, typename Value>
auto find(Range& r, Value const& value)
{
    // UFCS logic here, regular lookup will find the
    // begin/end declared above so that arrays can work
    auto first = r.begin();
    auto last = r.end();
    
    // ...
}
```

But obviously, everybody that wants to write their own custom algorithms isn't going to declare their own `begin()`{:.language-cpp} and `end()`{:.language-cpp} in each namespace that they write their algorithms. We're just going to do it the one time, and then make sure we bring them into scope. Since range is a common language concept, those clearly belong in `namespace std`{:.language-cpp}:

```cpp
namespace std {
    template <typename T, size_t N>
    auto begin(T (&arr)[N]) -> T* { return arr; }
    template <typename T, size_t N>
    auto end(T (&arr)[N])   -> T* { return arr+N; }
}

template <typename Range, typename Value>
auto find(Range& r, Value const& value)
{
    using std::begin, std::end;
    // UFCS logic here, regular lookup will find the
    // begin/end brought in with the using-declarations
    auto first = r.begin();
    auto last = r.end();
    
    // ...
}
```

But if we have to do this dance _anyway_ (the dance that Eric Niebler named the [Two Step](http://ericniebler.com/2014/10/21/customization-point-design-in-c11-and-beyond/)), then what have we actually gained from UFCS? The C++17 status quo, the code that we already have to write today without benefit of new features, looks like this:

```cpp
namespace std {
    // simplified from what's actually in std today
    template <typename T, size_t N>
    auto begin(T (&arr)[N]) -> T* { return arr; }
    template <typename C>
    auto begin(C& c) -> decltype(c.begin()) { return c.begin(); }
    
    template <typename T, size_t N>
    auto end(T (&arr)[N]) -> T* { return arr+N; }
    template <typename C>
    auto end(C& c) -> decltype(c.end()) { return c.end(); }    
}

template <typename Range, typename Value>
auto find(Range& r, Value const& value)
{
    using std::begin, std::end;
    // no UFCS necessary
    auto first = begin(r);
    auto last = end(r);
    
    // ...
}
```

Today's functional C++17 code looks just like the proposed UFCS code. We didn't actually gain anything. This is why I don't think UFCS helps the customization problem at all.

To be clear, I think the customization problem is a real problem. I think it very much merits a language solution. UFCS just isn't it.

Note that none of the above example is specific to `begin` or `end` as customization points. Given any concept that invites opt-in functionality from types you do not control, if any fundamental type needs to be supported (e.g. `int`{:.language-cpp}) or any compound type built up from fundamental types needs to be supported (e.g. `int*`{:.language-cpp} or `int[10]`{:.language-cpp} or `int(*)(int)`{:.language-cpp} or ...), we will run into the same problem.

## Extension

Conor Hoekstra gave a talk at CppNow about [Algorithm Intuition](https://www.youtube.com/watch?v=48gV1SNm3WA). It was a great talk, highly entertaining, good content. It very justifiably won all the awards. Go watch it.

One of the algorithm problems Conor presented (at around 1h09m mark) was: given a string of 0s and 1s, check if the longest stream of characters of the same value has length at least 7. The algorithm-free solution he presented looks like this (with minor edits):

```cpp
auto dangerous_team(std::string const& s) -> bool {
    auto max_players = 1, curr_players = 1;
    for (int i = 1; i < s.size(); ++i) {
        curr_players = s[i] == s[i - 1] ? curr_players + 1 : 1;
        max_players = std::max(max_players, curr_players);
    }
    return max_players >= 7;
}
```

Which he then turned into this solution with algorithms:

```cpp
auto dangerous_team(string const& s) -> bool {
    return adjacent_reduce(
        cbegin(s), cend(s),
        std::pair(1, 1),
        [](std::pair<int, int> acc, bool equal) {
            auto [mp, cp] = acc;
            cp = equal ? cp + 1 : 1;
            return std::pair(std::max(mp, cp), cp);
        },
        std::equal_to{})
        .first >= 7;
}
```

At this point, you might be wondering what this has anything to do with extension or unified function call syntax. Bear with me.

Now, to me, this code is extremely hard to understand. Even after watching that talk, twice, I still can barely grok it. And it's not Conor's fault - he points this out as well. The fundamental problem with the iterator model is that iterators can't compose. So we cannot break this problem up into small pieces that are easier for humans to understand - we need one giant algorithm hammer.

Compare the above to the Haskell solution he presented:

<pre style="background:#2d2d29;color:#ccc"><code><span style="color:#6196cc">dangerous_teams</span> <span class="token keyword">:: String -> Bool</span>
dangerous_teams <span class="token operator">=</span> (<span class="token operator">>=</span><span class="token number">7</span>)
                <span class="token operator">.</span> maximum
                <span class="token operator">.</span> map length
                <span class="token operator">.</span> group
</code></pre>

The thing you need to know about Haskell is that `.` is function composition, we read bottom to top, and Haskell is big on point-free functions: we don't provide the arguments unless we have to. That makes things a bit terse if you're not used to it, but it makes the style very declarative. You say _what_ you're doing, not so much how.

Anyway, so what we're doing is a `group` (which takes a `String` in this case and gives us a `[String]` - a list of strings where the consecutive characters are equal), then takes the lengths of each of those `String`s (`map length` is applying `length` to each element of that list), then takes the maximum of those lengths, and checks if it's at least 7. It's not one mega-algorithm, it's lots of little pieces.

But C++20 is upon is. It's a brand new era. We have Ranges. We don't have to resort to using non-composable iterator operations! We can use composable Range-based ones:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return s
         | views::group_by(std::equal_to{})
         | views::transform(ranges::distance)
         | ranges::any_of([](std::size_t s){
                return s >= 7;
            });
}
```

This reads basically the same as the Haskell solution. It's clear, it's declarative, it's nice and ordered. It's strictly better than Conor's presented solution for me not just because I can understand it at a glance but also because it's actually lazy (`any_of()`{:.language-cpp} will short-circuit).

But it also doesn't work.

Sure, it doesn't work because C++20 won't have `group_by` but that's not the reason I'm going for. It doesn't work because while the range adapters are pipeable, the algorithms are not. `group_by` and `transform` take in a range and emit a range, but `any_of` takes in a range and emits a `bool`{:.language-cpp} (as Conor notes in his talk, this range-to-value transformation is called a catamorphism).

I would have to write it this way:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return ranges::any_of(s
         | views::group_by(std::equal_to{})
         | views::transform(ranges::distance)
         , [](std::size_t s){
                return s >= 7;
            });
}
```

But I don't _want_ to write it this way. It completely breaks the directional flow of the algorithm here. We take a string, we group it by consecutive equal values, we take the lengths of those groups, and we see if any of those is larger than 7. We don't check if any of (take a string, group it by consecutive equal values and take the lengths of those groups) is larger than 7.

The range adapters work this way because `group_by` and `transform` and all their friends are written such that they can either take a range as their first argument... or take a bunch of stuff, return this partial object that has an `operator|()`{:.language-cpp} that takes a range on the left-hand side and invokes all the gathered arguments on it. This is work that has to be done for _each_ and _every_ range adapter. And it's not work that's been done for `any_of` or `all_of` or `accumulate` or ... It's not just mindless busywork either. In this partial application cases, you don't have enough information to constrain the call operator and you have to be careful with your overload sets. In general, this problem isn't even solveable before Concepts.

But with UFCS, we wouldn't have to think about this problem _at all_. We could just write code:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return s
         . views::group_by(std::equal_to{})
         . views::transform(ranges::distance)
         . ranges::any_of([](std::size_t s){
                return s >= 7;
            });
}
```

Yes, finally I got back to the point.

Now, none of the UFCS papers (as far as I'm aware) had any examples with qualified calls like this, but I would expect the above to work. Moreover, the above would work without anybody having to write these `operator|()`{:.language-cpp} things because the above would just evaluate as:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return ranges::any_of(
        views::transform(
            views::group_by(s, std::equal_to{}),
            ranges::distance)
        , [](std::size_t s){
                return s >= 7;
            });
}
```

This is much harder to read than the previous example, instead of reading top-down to follow the logic you have to read inside-out.

Let's back up and try to find the point I was making.

In this example, I know exactly what functions I want to call: `views::group_by`{:.language-cpp}, `views::transform`{:.language-cpp}, and `ranges::any_of`{:.language-cpp}. It's just that I want to call them linearly, not inside-out. Two of these happen to support the style of code I want to write, but the third doesn't (and may never). This is the extension problem: I know what I want to call, I just want to call it in a different way. Unlike the Customization problem presented earlier, this version of UFCS _does_ solve the Extension problem well.

## Why not UFCS?

The main driving argument against UFCS is that it can be very harmful to class stability. With the extension cases, let's say I write a bunch of code like the above except I bring in all these names so that I can use them unqualified. Maybe I have a lot of algorithms here, maybe I just hate qualifying names, whatever:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return s
         . group_by(std::equal_to{})
         . transform(ranges::distance)
         . any_of([](std::size_t s){
                return s >= 7;
            });
}
```

I wrote this code intending to call the non-member `view::group_by()`{:.language-cpp}, not any member function, despite the use of syntax that we would equate with member syntax. 

But what if, at some point, `std::string`{:.language-cpp} (or substitute the type of your choice in the context of your choice) adds a member function by one of these names? Maybe it's intended to be part of its API, maybe it's just a private helper function to help implement something else. Now suddenly maybe this code breaks because I'm picking up this new name and it's ambiguous, or private, or accepts different arguments. Worst case, maybe the call compiles but does something entirely unrelated to what I wanted it to do. Effectively: a class author can add a private member function to their class and suddenly name clash with user code. That's kinda terrifying. So much for library evolution.

How do we square the desire to have this potential for nicer call syntax with the desire for library authors to ever touch their code after it has any users?

## Why does it have to be <code style="background:#2d2d29"><span class="token operator">.</span></code>?

Here's my question. 

UFCS set out to solve two problems: customization (let the user define `foo` as either a member function or a non-member function, let the generic code not have to care) and extension (let the user call known non-member functions with member syntax). The customization problem means needing to call member functions, which surely implies using member syntax. But as I've demonstrated, UFCS isn't really sufficient to solve that problem anyway. And for the extension problem, if I know which function I'm calling, am I forced to use the same syntax? Why am I explicitly using member function syntax to call a non-member function? The same syntax which killed UFCS to begin with? 

Elixir, F#, Hack, Julia, and OCaml all have an operator spelled `|>`{:.language-cpp} (and there's an outstanding proposal to add the same in JavaScript). The operator does slightly different things in the three languages (naturally) but it's generally a way to split a function call. Instead of putting the function on the left and all the arguments on the right, the operator is a way to put an argument on the left on the function on the right.

In F#, Julia, and OCaml, the operator is evaluated as just calling the right hand side with the left hand side. That is, `x |> f`{:.language-cpp} evaluates as `f(x)`{:.language-cpp} and `x |> f(y)`{:.language-cpp} evaluates as `f(y)(x)`{:.language-cpp}. If we had the ability to write such a binary operator (as proposed in [P1282](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1282r0.html)), we could implement this in C++:

```cpp
template <typename Arg, std::invocable<Arg> F>
auto operator|>(Arg&& a, F&& f) -> std::invoke_result_t<F, Arg>
{
    return std::invoke(std::forward<F>(f), std::forward<Arg>(a));
}
```

This meaning doesn't seem helpful for the purposes of extension. It has the same problem that the range adapters have - you need to write out a partial call that has to return some object that is invocable. Technically, it _is_ easier - instead of returning an object that is left-pipeable, we would be able to return an object that is just invocable (e.g. a lambda).

Elixir's version of `|>`{:.language-cpp} is a little different. The right-hand side isn't completely evaluated, rather the left-hand argument is inserted into the argument list. That is, `x |> f`{:.language-cpp} still evaluates as `f(x)`{:.language-cpp} as before... but `x |> f(y)`{:.language-cpp} evaluates as `f(x, y)`{:.language-cpp}. Importantly, this is not a new operator - this latter example does not separately evaluate `f(y)`{:.language-cpp}, it _only_ evaluates `f(x, y)`{:.language-cpp}. In the same way that `x.f(y)`{:.language-cpp} today does not mean `operator.(x, f(y))`{:.language-cpp}.

Now, Hack's meaning of `|>`{:.language-cpp} is more in line with Elixir's, just more explicit and more generalized. Rather than the F#/Julia/OCaml route of just invoking the right-hand side with the left-hand side, we do use the left-hand side as an argument into the right-hand function. Except that unlike Elixir, this argument both has to be explicit and does not have to be the first argument. Hack uses `$$`{:.language-cpp} to denote that mandatory placeholder:

```cpp
$x = vec[2,1,3]
  |> Vec\map($$, $a ==> $a * $a)
  |> Vec\sort($$);
```

Where in Elixir, we would write `x |> f(y)`{:.language-cpp}, in Hask we would have to write `x |> f($$, y)`{:.language-cpp}, both of which evaluate directly as `f(x, y)`{:.language-cpp}. But Hask also would allow the writing of `x |> f(y, $$)`{:.language-cpp}, which means `f(y, x)`{:.language-cpp}. More explicit, yet more flexible.

Let's consider Elixir's approach for the extension problem. This meaning would directly allow for:

```cpp
auto dangerous_teams(std::string const& s) -> bool {
    return s
         |> group_by(std::equal_to{})
         |> transform(ranges::distance)
         |> any_of([](std::size_t s){
                return s >= 7;
            });
}
```

It would not require library authors to painstakingly write their adapters and algorithms to allow for `|`{:.language-cpp}-based usage. It would save us the time of figuring out whether we can even make all of the catamorphisms pipeable, and if we can, making them such. It would give us the major selling point of UFCS, completely sidestepping the major failing point of UFCS.

All at the cost of just having a new token that every parser would have to handle and a new kind of call syntax.

And the inevitable war between `west(invocable)`{:.language-cpp} and <code style="background:#2d2d29;color:#ffffff">invocable <span class="token operator">|></span> <span class="token function">east</span></code>.