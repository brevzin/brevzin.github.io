---
layout: post
title: "Using Token Sequences to Iterate Ranges"
category: c++
tags:
 - c++
 - c++29
 - ranges
---

There was a StackOverflow question recently that led me to want to write a new post about Ranges. Specifically, I wanted to write about some situations in which Ranges do more work than it seems like they should have to. And then what we can do to avoid doing that extra work. I'll offer solutions — one sane one, which you can already use today, and one pretty crazy one, which is using a language feature we're still working on designing, which may not even exist in C++29.

## The Problem

For the purposes of this post, I'm just going to talk about the very simple problem of:

```cpp
for (auto elem : r) {
    use(elem);
}
```

In the C++ iterator model, this desugars into something like:

```cpp
auto __it = r.begin();
auto __end = r.end();

while (__it != __end) {
    use(*__it);

    ++__it;
}
```

I used a `while` loop here deliberately, because it's a simpler construct and it lets me write the advance step last.

Now, if you want to customize the behavior of a range, those are your entry points right there. You can change what the initialization phase does (`begin()` and `end()`), you can change the check against completeness (`__it != __end`), you can change the read operation (`*__it`), and you can change the advance operation (`++__it`). That's it. You can't change the structure of the loop itself.

That alone is enough to offer a pretty large wealth of functionality. It's a very powerful abstraction.

The Ranges library has a bunch of range adaptors which customize this behavior. Some of them very neatly slot into this set of customization points. `views::transform` just changes what `*__it` does. `views::drop` just changes what `r.begin()` does. These adaptors have no overhead.

Now, it might not be surprising to learn that an adaptor like `views::join` has some overhead. `views::join` really wants to write two nested loops, but it can't — it has to flatten the iteration somehow. Or `views::concat`, which wants to write `N` loops instead of just one, but it can't do that either. But there are a few adapters which seem like they should slot into this model very neatly. And yet...

### Why does it always have to be `views::filter`?

Somehow, no matter the topic, `views::filter` is always a problem.

In this case, it seems like `filter` fits the model very nicely. It needs to customize `begin()` and `++__it`, both of which are ready-made customization points. The check and read operations are pass-through. So what's the deal?

Well, let's go ahead and desugar what `filter(f)` does to our loop:

```cpp
while (__it != __end) {         // (A)
    use(*__it);

    ++__it;

    // now we have to do find_if(f)
    while (__it != __end) {     // (B)
        if (f(*__it)) {
            break;              // (C)
        }
        ++__it;
    }
}
```
{: data-line="1,7,9" .line-numbers }

Consider the three marked lines. When we do the `find_if` to find our next element, we have to make sure that we don't run off the end of our range. That's the check in `(B)`. And then we keep looking for an element until we satisfy our predicate. Now, that inner loop will terminate in one of two ways:

1. We hit the end — the check in `(B)` failed. This means the check in `(A)` will also, of course, fail, and is redundant.
2. We found an element — we hit the `break` in `(C)`. This means the check in `(A)` will definitely pass, and is redundant.

In theory, we only have to do `N` comparisons between `__it` and `__end` (one for each element in the original range). The optimal loop would be something like this:

```cpp
while (__it != __end) {
    if (f(*__it)) {
        use(*__it);
    }

    ++__it;
}
```

But instead, we do `N + K + 1` comparisons, where `K` is the number of elements that satisfy the predicate. It's possible those extra `K+1` comparisons get optimized out, if the underlying iterator is really just something like a pointer. But the existence of those extra comparisons messes with the optimizer. It also doesn't help that `f` isn't inlined into the iterator and tends to be accessed via a back-pointer to the `filter_view`.

`K + 1` extra pointer comparisons might not sound like a big deal. But what if our comparison was more expensive than that?

### It gets worse with `views::take_while`

The actual [StackOverflow question](https://stackoverflow.com/q/79539857/2069064) I alluded to earlier didn't just use `filter`, it did `take_while(f) | filter(g)`. Just like `views::filter` seemingly only needs to adjust `++__it`, `views::take_while` seemingly only needs to adjust `__it != __end`. It... should fit right in.

And yet, if we desugar what `r | take_while(f) | filter(g)` actually does, we get this:

```cpp
while (__it != __end and f(*__it)) {       // (A)
    use(*__it);


    ++__it;
    // now we have to do find_if(g)
    // except now bounded by take_while(f)
    while (__it != __end and f(*__it)) {   // (B)
        if (g(*__it)) {
            break;                         // (C)
        }
        ++__it;
    }
}
```
{: data-line="1,8,10" .line-numbers }

Now let's consider what happens as we exit the inner loop. There are three cases:

1. We hit the true end in `(B)`. Now we again check that `__it != __end` which will of course fail, there's our 1 redundant iterator comparison again.
2. We hit an element that breaks our `take_while` criteria — an element for which `f` returns `false`. But we have to do that check in `(A)` again, which requires invoking `f` again on the same element!
3. We hit an element that satisfies our filter `g`. We have already verified that it satisfies `f`, but now we... again have to invoke `f` in `(A)`!

Or, put differently. When `(B)` becomes `false`, we're out of elements — but we recheck `(A)` even though it has to be `false` again. But when we break in `(C)`, we still have to recheck `(A)` again even though it has to be `true`.

What that means is that this program:

```cpp
auto lt5 = [](int i){ println("lt5({})", i); return i < 5; };
auto even = [](int i) { println("even({})", i); return i % 2 == 0; };

auto v = vector<int>{1, 2, 3, 4, 5, 6, 7, 8, 9};
auto r = v | views::take_while(lt5) | views::filter(even);
for (int i : r) {
    println("got {}", i);
}
```

will print [the following](https://godbolt.org/z/8ceYd56oK):

```
lt5(1)
even(1)
lt5(2)
even(2)
lt5(2)
* got 2
lt5(3)
even(3)
lt5(4)
even(4)
lt5(4)
* got 4
lt5(5)
lt5(5)
```

Note that we call `lt5` 8 times on those 5 elements. In this case, the function is very cheap (or would be if we weren't printing). But what if it weren't?

### Flip it and `views::reverse` it

Here's the question: what happens if we throw a `views::reverse` at this range? At initial glance, maybe `views::reverse` should do pretty well — since we basically just have to change `++__it` to `--__it`.

Right?

It turns out that reversing a range is one of those sneakily complicated algorithms, that a lot of people will get wrong the first couple times they try to write it. Even writing it with integers can be tricky because of unsigned integers wrapping at `0`. But with iterators you just _cannot_ iterate past `begin()`. So you have to structure your loop this way:

```cpp
auto __it = r.begin();
auto __end = r.end();
while (__it != __end) {
    // decrement FIRST
    --__end;

    // THEN read
    use(*__end);
}
```

You might recognize this as being a very different loop structure than the forward loop — where we read then increment. So just flipping increment to decrement is insufficient. Instead, we have to do that decrement in the only place we can do it — [within the read operation](https://eel.is/c++draft/reverse.iterators#reverse.iter.elem-1). So our loop is:

```cpp
while (__it != __end) {
    auto __tmp = __end;
    --__tmp;
    use(*__tmp);

    --__end;
}
```

It's hard to miss the overhead here: we're decrementing the same iterator twice on every iteration. Which, if the underlying iterator is just a pointer, is not a big deal. And for many iterators increment and decrement aren't that expensive. But if moving around our iterator has to do a linear search, like `views::filter`s would?

Well then. This program:

```cpp
auto v = vector<int>{1, 2, 3, 4, 5, 6, 7, 8, 9};
auto r = v | views::take_while(lt5) | views::filter(even) | views::reverse;
for (int i : r) {
    println("* got {}", i);
}
```

now prints:

```
lt5(1)
even(1)
lt5(2)
even(2)
lt5(2)
lt5(3)
even(3)
lt5(4)
even(4)
lt5(4)
lt5(5)
lt5(5)
even(4)
* got 4
even(4)
even(3)
even(2)
* got 2
even(3)
even(2)
```

That is, we have the same 8 calls to `lt5` for our initial five elements — nothing changes there. But before we actually only had the exact 4 calls to `even` that we needed. Now, we have 10. This is not an amazing place to end up.

> Incidentally, I wrote a post recently on [mutating through a filter]({% post_url 2023-04-25-mutating-filter %}) which laid out the case to avoid as multi-pass mutation. Because of this double-decrementing logic, `views::reverse` _is_ a multi-pass algorithm. I'll get back to this later.
{:.prompt-info}



We find ourselves in a place where Ranges code is quite far from zero-overhead. It would be nice if this weren't the case. Is there something that we could do differently in order to avoid this problem?

## The Sane Solution: Flux

I have already promised you two solutions, and you've read this far, so let's get to it.

Tristan Brindle has a library called [Flux](https://github.com/tcbrindle/flux). He has given a number of conference talks about it, whose titles usually have "Iteration Revisited" in them (for instance, [this one from CppCon 2023](https://www.youtube.com/watch?v=nDyjCMnTu7o)). Highly recommend checking it out the talks and the library.

The highly abridged version of Flux is that it's actually quite similar to C++20 Ranges. The main difference really is that a Flux cursor (as opposed to a C++ iterator) is dumb — it does not know how to advance itself or read itself. So whereas the C++ loop I presented earlier is:

```cpp
auto __it = r.begin();
auto __end = r.end();

while (__it != __end) {
    use(*__it);

    ++__it;
}
```

the Flux loop is:

```cpp
auto __cursor = flux::first(r);

while (not flux::is_last(r, __cursor)) {
    use(flux::read_at(r, __cursor));
    flux::inc(r, __cursor);
}
```

If it looks very similar to you, that's because it _is_ very similar. Indeed, Flux and C++ Ranges are isomorphic. It is quite easy to map from one to the other.

And, indeed, if you just do the same thing in Flux as we just did in C++, we get [the same behavior](https://godbolt.org/z/PGoshMTd1):

```cpp
auto v = vector<int>{1, 2, 3, 4, 5, 6, 7, 8, 9};
auto r = flux::ref(v).take_while(lt5).filter(even);
for (int i : r) {
    println("* got {}", i);
}
```

This has the same 8 calls to `lt5`.

> Flux doesn't actually support `reverse()` on this list. In order for Ranges to support it, it has to eagerly process the `take_while`. Flux apparently chooses [not to](https://github.com/tcbrindle/flux/blob/504a107204a2fc3cd67eada992b987b21dbbbbd2/include/flux/adaptor/take_while.hpp#L71) do that.
{:.prompt-info}

At this point you're probably wondering why I possibly described this as the sane solution, given that it has identical behavior.

Tristan has one trick up his sleeve. You could, instead, do this:

```cpp
flux::ref(v)
    .take_while(lt5)
    .filter(even)
    .for_each([](int i){
        println("* got {}", i);
    });
```

Seemingly the same thing, except we're using the `for_each` algorithm instead of the `for` loop. And now, we have [a different outcome](https://godbolt.org/z/h7KKae3zj):

```
lt5(1)
even(1)
lt5(2)
even(2)
* got 2
lt5(3)
even(3)
lt5(4)
even(4)
* got 4
lt5(5)
```

That's just five calls to `lt5` — the correct amount.

This is the power of _internal iteration_. In Flux, `for_each` isn't just a wrapper around writing the loop I showed earlier. It can do better by not being confined to having to fit within the same, rigid loop structure. Internally, Flux can iterate however it wants — because you cannot observe it anyway.

Among other issues, internal iteration also resolves the well-known `transform(f) | filter(g)` problem where `f` gets invoked twice for every element that satisfies `g`.

### Space Consideration

Now, one of the other significant benefits of Flux — it's not just all about the internal iteration customization point — is how the layering ends up happening. Let's take that same `r | transform(f) | filter(g)` example and think about what it actually looks like. You'll end up with an object — the view — which is going to have `r`, `f`, and `g` in it. That's not surprising. But what do the iterators look like? They'll have an iterator into `r`, but also a pointer to the `transform_view` (to get at `f` — or maybe just a pointer to the `F`) and a pointer to the `filter_view` (to get at both `g` and the `transform_view`).

Or, to put it visually, something like this:

```cpp
struct the_view {
    R underlying; // the underlying range
    F f;          // the transform function
    G g;          // the filter predicate
};


struct the_iterator {
    iterator_t<R> underlying;   // the underlying iterator
    F* f;                       // pointer to the transform function
    the_view* parent;           // pointer to the view (for filter)
};
```

There is a fairly glaring issue here. Why does `the_iterator` need _both_ `F*` _and_ `the_view*` members? Given that you could already get at the function via `parent->f`? Ranges just doesn't work like that. Wrapping happens incrementally. There's no point at which we could attempt to finalize our pipeline in order to optimize our space usage. The `transform_view` just doesn't know about the next `filter_view`. Moreover, because `the_iterator` gets a lot of information through pointer chasing, it is pretty likely that this negatively affects optimization.

In Flux, on the other hand, our structure looks like this:

```cpp
struct the_sequence {
    R underlying; // the underlying range
    F f;          // the transform function
    G g;          // the filter predicate
};

struct the_cursor {
    cursor_t<R> underlying; // the underlying cursor
};
```

Here, `the_sequence` looks identical to what we had for `the_view`. But `the_cursor`... wait, where did all the members go? Remember that a Flux cursor doesn't know how to advance or read itself — you need the sequence handy in order to do these things. But neither `filter` nor `transform` need to do anything special with the cursor, they don't even wrap it.

And there is no need for any pointers anywhere — everything is purely done as a matter of composition. Less pointer chasing is more optimizer friendly, which is likely why otherwise equivalent Flux pipelines optimize better.

Notably, since Flux and Ranges are isomorphic, you can produce a C++ iterator out of any Flux sequence. And what does that iterator look like? It's just a pair of the cursor and a pointer to the sequence. Effectively, taking a Flux pipeline and then turning it into a C++ iterator performs that kind of finalizing space operation.

Pretty cool.


## The Wild Solution: Token Sequences

Some of you might be thinking that this is boring. Buckle your seatbelt, Dorothy. Kansas is about to go bye-bye.

While Reflection is full speed ahead for C++26, we're primarily only going to get tools for _introspection_. Not much in the way of code _generation_. Even just introspection will be a tremendous and transformative addition to the language, and I am extremely excited about it. Adding more was just not in the cards. There is only so much time, and even [P2996](https://wg21.link/p2996) is enormous.

One of our ideas that we've been working on for injection is called [Token Sequences](https://wg21.link/p3294). The short version of the pitch is that the best way to represent C++ code is C++ code, so we want C++ code injection to look as much as C++ code as possible. To the point where we think a raw, unchecked sequence of tokens is the best approach. There is a partial (occasionally buggy) implementation that Daveed Vandedoorde did in EDG that I'll be demonstrating here.

> Also check out his [CppCon Reflection Keynote](https://www.youtube.com/watch?v=wpjiowJW2ks)!
{:.prompt-info}

The goal of this post isn't to really explain the design or motivate its specific details. It's instead to demonstrate the kinds of shenanigans you can do with it. Maybe this could eventually inform what the right way to specify internal iteration for ranges will be? Who knows.

The key issue I've harped on in this blog post is that the loop structure in C++ is _fixed_. It _has_ to look like this:

```cpp
auto __it = r.begin();
auto __end = r.end();

while (__it != __end) {
    use(*__it);

    ++__it;
}
```

And if your algorithm wants a slightly different structure — then you're out of luck. For instance, `take_while(f)` wants to do this:

```cpp
auto __it = r.begin();
auto __end = r.end();

while (__it != __end) {
    if (not f(*__it)) {
        break;
    }

    use(*__it);

    ++__it;
}
```


And `filter(g)` wants to do this:

```cpp
auto __it = r.begin();
auto __end = r.end();

while (__it != __end) {
    if (g(*__it)) {
        use(*__it);
    }

    ++__it;
}
```

And `reverse` wants to write that completely different loop I showed earlier where we decrement then read.

What if... we just _could_ write whatever loop we wanted? Wouldn't we just write the optimal loop? Let's do that!

### The Signature

We're going to copy the structure of the range-based `for` loop — the same structure every other language uses too. That is, we're going to have a loop with three pieces:

1. the loop element
2. the range
3. the body

Each of these are just token sequences. We'll have a function that takes those three pieces and injects the correct loop for them:

```cpp
consteval auto for2(info init, info range, info body) -> void {
    // ...
}
```

Which we will invoke like this:

```cpp
consteval {
    for2(
        ^^{ int i },
        ^^{
            v
            | views::take_while(lt5)
            | views::filter(even)
            | views::reverse
        }
        ^^{
            println("* got {}", i);
        });
}
```

Here we have three token sequences that already are three very different things. The first is a declaration, without a semicolon. The second is an expression. The third is sequence of statements. But they all share the same syntax.

What `for2` has to do is figure out what loop to inject based on the range we're iterating over. But we don't have a range _type_. We have a ... token sequence. How do we get the type out of it? Before I get into those details, let's first back up and talk about the model.

### The Model

Ultimately, we're going to do something very similar to what Tristan did in Flux. Internally iterating a `filter_view` means internally iterating the underlying view and just only conditionally executing the body. Internally iterating a `transform_view` means internally iterating the underlying view and applying an extra operation before passing on the element. Internally iterating a `take_while_view` means internally iterating the underlying view and potentially breaking early.

Going one piece at a time, the loop we want to emit for just `v` is going to look like this:

```cpp
auto&& __r0 = v;
auto __it = __r0.begin();
auto __end = __r0.end();
for (; __it != __end; ++it) {
    int i = *__it;
    println("* got {}", i);
}
```

The loop we want to emit for `v | views::take_while(lt5)` would be this:

```cpp
auto&& __r0 = v | views::take_while(lt5);
auto&& __r1 = __r0.base();    // the underlying
auto&& __pred1 = __r0.pred(); // the take-while predicate (lt5)

auto __it = __r1.begin();
auto __end = __r1.end();
for (; __it != __end; ++it) {
    auto&& __elem1 = *__it;
    if (not __pred1(__elem1)) {
        break;
    }

    int i = __elem1;
    println("* got {}", i);
}
```

The loop we want to emit for `v | views::take_while(lt5) | views::filter(even)` would be this:

```cpp
auto&& __r0 = v | views::take_while(lt5) | views::filter(even);
auto&& __r1 = __r0.base();
auto&& __pred1 = __r0.pred(); // the filter predicate (even)
auto&& __r2 = __r1.base();    // the underlying
auto&& __pred2 = __r1.pred(); // the take-while predicate (lt5)

auto __it = __r2.begin();
auto __end = __r2.end();
for (; __it != __end; ++it) {
    auto&& __elem2 = *__it;
    if (not __pred2(__elem1)) {
        break;
    }

    auto&& __elem1 = __elem2;
    if (__pred1(__elem1)) {
        int i = __elem1;
        println("* got {}", i);
    }
}
```

What we have to do is treat the range as an expression template, and slowly peel off the layers. Conceptually, the recursion is not that complicated — nor is it altogether different from what you would write in direct template code attempting to implement in a sane way. It's pretty novel to actually see it in this form though — even if this is a fairly straightforward loop to write by hand (although presumably with better identifiers that don't have to alias each other).

But what does this look like with token sequences, where we only have a token sequence, and we don't even have a type at all?

### Token Sequences All The Way Down

Sometimes, when all you have a token-sequence-injection-shaped hammer, the solution is a token-sequence-injection-shaped nail. In this case, we can just inject our way into a solution.

Specifically, let's fill in the details on `for2`. It looks like this:

```cpp
consteval auto for2(info init, info range, info body) -> void
{
    inject_tokens(^^{
        {
            auto&& __r0 = \tokens(range);
            using __R0 = std::remove_cvref_t<decltype(__r0)>;
            inject_tokens_impl<__R0, 0>::apply(Direction::forward, \(init), \(body));
        }
    });
}
```

That is — we start by injecting our range (as `__r0`). Now that's a normal variable, whose type we can grab (as `__R0`). And we can actually just recursively inject from there.

Yes, we are injecting a token sequence, whose evaluation will inject another token sequence.

> Token-sequence-ception.
{:.prompt-info}

I have two helpers that I used to implement this. One is a simple enum class for which direction we are iterating:

```cpp
enum class Direction { forward, reverse };
consteval auto operator!(Direction d) -> Direction {
    return d == Direction::forward ? Direction::reverse : Direction::forward;
}
```

And the other is a wrapper for the real token sequence primitive for injection.

```cpp
consteval auto inject_tokens(info tokens) -> void {
    // __report_tokens(tokens);
    queue_injection(tokens);
}
```

`std::meta::queue_injection` actually injects the provided token sequence. But EDG has a nice little utility called `__report_tokens` that prints them to the console. This is pretty essential in debugging.

Alright, so first let's start with our base layer. If we haven't customized iterating over our range in any way, we'll just directly emit the simple for loop we need:

```cpp
template <class R, int I>
struct inject_tokens_impl {
    static consteval auto apply(Direction d, info init, info body) -> void {
        if (d == Direction::forward) {
            inject_tokens(^^{
                {
                    auto __it = \id("__r"sv, I).begin();
                    auto __end = \id("__r"sv, I).end();
                    for (; __it != __end; ++__it) {
                        \tokens(init) = *__it;
                        \tokens(body);
                    }
                }
            });
        } else {
            inject_tokens(^^{
                {
                    auto __begin = \id("__r"sv, I).begin();
                    auto __end = \id("__r"sv, I).end();
                    while (__begin != __end) {
                        --__end;
                        \tokens(init) = *__end;
                        \tokens(body);
                    }
                }
            });
        }
    }
};
```

`inject_tokens_impl<R, I>` is implicitly iterating over the range `__r{I}`.

The interpolation syntax `\id("__r", I)` is what I'm using to create the _identifier_ `__r1`, `__r2`, etc. It can take a sequence of strings and integers (starting with a string) and just concatenates them together. Everything else does what it looks like it does. Note that I'm emitting the direct, efficient reverse loop — rather than going through reverse iterators.

The recursion step for `filter_view` doesn't care which direction we are iterating in — we just need to insert a branch:

```cpp
template <class R, class P, int I>
struct inject_tokens_impl<std::ranges::filter_view<R, P>, I> {
    static consteval auto apply(Direction dir, info init, info body) -> void {
        inject_tokens(^^{ auto \id("__r"sv, I+1) = \id("__r"sv, I).base(); });
        inject_tokens(^^{ auto \id("__pred"sv, I+1) = \id("__r"sv, I).pred(); });
        inject_tokens_impl<R, I+1>::apply(dir,
            ^^{ auto&& \id("__elem"sv, I+1) },
            ^^{
                if (\id("__pred"sv, I+1)(\id("__elem"sv, I+1))) {
                    \tokens(init) = \id("__elem"sv, I+1);
                    \tokens(body);
                }
            }
        );
    }
};
```

Here, range `I` is implicitly iterating over underlying range `I+1` and passing through its contents to the next ranges `init` variable and `body` only if we satisfy the predicate. We're producing a range `__r{I+1}` for the next stage to iterate over.

The recursion step for `transform_view` looks very similar to filter, and indeed is simpler because you don't even have to write an `if` statement. It's just that while `filter_view` provides a convenient` pred()`, `transform_view` has no such equivalent `func()`:

```cpp
template <class R, class F, int I>
struct inject_tokens_impl<std::ranges::transform_view<R, F>, I> {
    static consteval auto apply(Direction dir, info init, info body) -> void {
        inject_tokens(^^{ auto \id("__r"sv, I+1) = \id("__r"sv, I).base(); });

        // the function is the 2nd member, and is a movable-box<F>, so we can
        // pull it out that way and then dereference it
        constexpr auto box = nonstatic_data_members_of(
            ^^std::ranges::transform_view<R, F>)[1];
        inject_tokens(
            ^^{ auto \id("__func"sv, I+1) = *\id("__r"sv, I).[:\(box):]; });

        inject_tokens_impl<R, I+1>::apply(dir,
            ^^{ auto&& \id("__elem"sv, I+1) },
            ^^{
                \tokens(init) = \id("__func"sv, I+1)(\id("__elem"sv, I+1));
                \tokens(body);
            }
        );
    }
};
```

The recursion step for `take_while_view` looks quite different because we actually have to do very different things based on direction. If we're iterating forwards, we have to `break` early. If we're iterating backwards, we have to first find where we need to stop. The reverse iteration pretends that we're iterating over that `subrange` (so we introduce an `__r{I}_full` that is the real one and then an `__r{I}` that is the `subrange`):

```cpp
template <class R, class P, int I>
struct inject_tokens_impl<std::ranges::take_while_view<R, P>, I> {
    static consteval auto apply(Direction dir, info init, info body) -> void {
        if (dir == Direction::forward) {
            apply_forward(init, body);
        } else {
            apply_reverse(init, body);
        }
    }

    static consteval auto apply_forward(info init, info body) -> void {
        inject_tokens(^^{ auto \id("__r"sv, I+1) = \id("__r"sv, I).base(); });
        inject_tokens(^^{ auto \id("__pred"sv, I+1) = \id("__r"sv, I).pred(); });
        inject_tokens_impl<R, I+1>::apply(Direction::forward,
            ^^{ auto&& \id("__elem"sv, I+1) },
            ^^{
                if (not \id("__pred"sv, I+1)(\id("__elem"sv, I+1))) {
                    break;
                }

                \tokens(init) = \id("__elem"sv, I+1);
                \tokens(body);
            }
        );
    }

    static consteval auto apply_reverse(info init, info body) -> void {
        inject_tokens(^^{
            auto \id("__r"sv, I+1, "__full"sv) = \id("__r"sv, I).base(); });
        inject_tokens(^^{
            auto \id("__pred"sv, I+1) = \id("__r"sv, I).pred(); });

        inject_tokens(^^{
            auto \id("__r"sv, I+1) = std::ranges::subrange(
                std::ranges::begin(\id("__r"sv, I+1, "__full"sv)),
                std::ranges::find_if_not(
                    \id("__r"sv, I+1, "__full"sv),
                    \id("__pred"sv, I+1)));
        });

        inject_tokens_impl<R, I+1>::apply(Direction::reverse, init, body);
    }
};
```

Again, the conceptual logic here is not complicated. The fact that we're injecting token sequences which inject token sequences is _very_ complicated. And some of the syntax and implementation choices make it a bit hard to read. In particular, `queue_injection` cannot take multiple declarations — which is why this is three repeated calls to `inject_tokens` and not just one that injects all three variables.

### What About Control Flow?

As I showed in the model — the loop body that you are passing to `for2` is actually injected in _a loop_. The correct, optimal loop for the range you requested. That means that `break` and `continue` just work. And because I'm just not injecting any function scopes, `return` just works too. That's a pretty huge boon for convenience.

Flux can't do that.

### Let's See It!

You can see it in action [here](https://godbolt.org/z/bdM1do49n).

The code is iterating over the same range we've seen in action — first using Ranges direction, and then again using code injection. You can see that even the reversed version leads to _just_ five calls to `lt5` (optimal) and four calls to `is_even` (optimal). Even though we're reversing through a filter! Pretty incredible.

Throw a `transform` [in there](https://godbolt.org/z/qdPcdnqv9), just for good measure, and we get the following counts:

||Ranges-based iteration|Injection-based internal iteration|
|-|-|-|
|`lt5`|8|5|
|`square`|12|4|
|`even`|10|4|

Earlier, in an aside, I called out the problem of mutating in a multi-pass algorithm over with a `filter` and noted that `reverse` was just such a multi-pass algorithm.

Consider what happens if we did this:

```cpp
auto v = std::vector<int>{1, 2, 3, 4, 5, 6, 7, 8, 9};
auto r = v | views::filter(is_even) | views::reverse;
for (int& i : r) {
    ++i;
}
```

What do you expect the new values of `v` to be? Did you expect this?

```
   1 2 3 4 5 6 7 8 9
=> 1 2 3 5 5 6 7 9 9
```

Note that only every other element is incremented. The `4` and the `8` were incremented, the `2` and `6` were not. That's because of shenanigans with multi-pass mutation.

> This has nothing to do with `views::filter` caching. See [my older post]({% post_url 2023-04-25-mutating-filter %}) for another example of such element skipping.
{:.prompt-info}

Now what happens if `v` actually ended with an even number instead of an odd number? What if we add `10` at the end? Not we simply segfault! Because we run off the end of the vector. Again, multi-pass mutation shenanigans.

What happens if, instead, we use our fancy new token-sequence injecting monstrosity?

```cpp
consteval {
    for2(
        ^^{ int& i },
        ^^{ v  | std::views::filter(is_even) | std::views::reverse },
        ^^{
            i += 1;
        });
}
```

No problem! [Works great](https://godbolt.org/z/881Gf7rsn) (And if you add `10` at the end, no segfault — the `10` gets incremented):

```
   1 2 3 4 5 6 7 8 9
=> 1 3 3 5 5 7 7 9 9
```

This works without issue because I'm just directly emitting the correct underlying loop. And that loop is just doing a single pass through `v`, not two.

## Where Do We Go From Here

There are several ways to answer this question.

On the token sequence front, we're all currently spending all of our time on P2996 to get Reflection into C++26. But eventually we will get back to working on token sequences and try to figure out how to make it work. There are very many design questions.

On the Ranges front, I do think we need to think about how to do a customization point for internal iteration. Jonathan Müller and I wrote this paper a couple years ago about a [generator-based for loop](https://wg21.link/p2881). The problem there is that I really think the right way to express this is as a coroutine — the function-based sink approach really muddles things. Perhaps something like:

```cpp
template <input_range V, indirect_unary_predicate<iterator_t<V>> Pred>
    requires /* ... */
class filter_view : public view_interface<filter_view<V, Pred>> {
    V base_ = V();
    movable_box<Pred> pred_;

public:
    constexpr operator for() -> generator<range_reference_t<V>> {
        for (auto&& elem : base_) {
            if (invoke(pred_, elem)) {
                co_yield elem;
            }
        }
    }
};
```

I think most people would agree that this is easier to read that everything I wrote in the token sequence implementation? But I think remains to be seen how well C++20 generators actually optimize. I don't think GCC even tries to optimize the allocation away yet.

A library solution on the Ranges front would be to do what Tristan did in Flux — provide a `for_each_while()` customization point on each range adaptor. And, importantly, redirect all the single-pass algorithms that we have through that customization point. There are many such — `any_of`, `all_of`, `count`, `fold_left`, `copy`, etc. That could potentially be a big performance win.

> Then again, I said the same thing about [output iterators]({% post_url 2022-02-06-output-iterators %})... three years ago. And I still haven't done anything there either. Although I wasn't wrong!
{:.prompt-info}

The library solution to internal iteration is easily achievable. Just takes work. The language feature for internal iteration somehow to me seems more complicated than getting token sequences right, so I'm going to spend my time on the latter instead.

But if you want a solution now — use Flux.