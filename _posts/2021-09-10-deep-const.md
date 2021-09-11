---
layout: post
title: "Coercing deep const-ness"
category: c++
tags:
  - c++
  - c++20
  - ranges
pubdraft: yes
---

In C++, template deduction doesn't allow for any conversion. A type matches the pattern, or it's a deduction failure. But there's one sort-of exception to this rule, and it's an exception that everyone has taken advantage of:

```cpp
template <typename T>
void takes_ptr(T const*);

void f(int i) {
    takes_ptr(&i);
}
```

`&i` here has type `int*`. There is no `T` for which that is some `T const*`, but this compiles and works anyway. An even more common and familiar idiom would be the reference version of this:

```cpp
template <typename T>
void takes_ref(T const&);
```

Even if you pass a mutable `int` to `takes_ref`, that compiles just fine, and we end up with a function template that both *enforces* and *coerces* that it does not mutate its argument. This `const`-qualification exception to the template deduction doesn't allow conversions rule is mighty handy.

### Enforcing deep const with `span`

With `span`, the way we express a function that doesn't have mutable access to elements is:

```cpp
void takes_const_span(span<int const>);
```

Note that it's `span<T const>` and not `span<T> const&` - `span` has reference semantics and thus is shallow const, and the important const for us in this situation is the *inner* one. A `span<int const>` cannot mutate its elements (but is itself mutable) while `span<int> const` can mutate its elements (but is itself const). Similar to the difference between `const T*` and `T* const`.

With `takes_const_span()` as written, you can pass a `vector<int>` or a `vector<int> const` -- both of those invocations work just fine, and regardless of whether the original `vector` is mutable or not, the function has no mutable access. This is part of why `span` is such a useful type -- it is very easy to express and enforce constness like this.

Now, what if we combined these two ideas: using `span` to express deep const-ness while also trying to be more generic across all types and wanting to take advantage of the const-qualification exception? Maybe I have some non-mutating algorithm that works on *all* contiguous ranges, not just those comprised of `int`s? 

```cpp
template <typename T>
void takes_generic_const_span(span<T const>);
```

This one, though, is just about completely useless.

The const-qualification rule only applies to pointers and references. `span` is neither of those, so we're reduced to the default rule that templates do not allow conversions.

That means not only that I can pass neither `vector<int>` nor `vector<int> const` into this algorithm (because while both are *convertible* to some kind of `span<T const>`, neither *are* `span<T const>`)... but also that I can't even pass a `span<int>` into this function! The latter doesn't work because, well obviously a `span<int>` is not some kind of `span<T const>`. We have no way of expressing in the language that we want the const-qualification rule to apply here.

Although even if we did, it'd be insufficient, since allowing `span<int>` is good (or even, a bare minimum requirement) but we really also want to allow `vector<int>`.

### Enforcing deep const with a template?

Okay, so the `span<T const>` approach clearly doesn't work. Is there an alternative that we could try?

```cpp
template <contiguous_range R>
    requires constant_range<R>
void takes_contiguous_const_range(R&& r);
```

Here, `constant_range` is a concept which enforces that `R` is, well, a constant range. Turns out this is a tricky thing to get right -- because a range of prvalue `int`s isn't mutable, so it should count as const, but a range of prvalue `tuple<int&>`s (or `vector<bool>::reference`) is mutable, so it shouldn't. See [my paper](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p2278r0.html#act-iv-stdconst_iterator) for more on this topic. Although given that we're requiring contiguity, we don't really need the trickiness of `constant_range`, it would be sufficient to check that `remove_reference_t<range_reference_t<R>>` is `const`.

This attempt, though, has one big flaw. It *requires* that the incoming range be constant, but it can't *coerce* the incoming range to become constant. Let's go back to our pointer example real quick.

```cpp
template <typename T>
void takes_ptr(T const*);

void f(int i) {
    takes_ptr(&i);
}
```

Imagine if the template rules were a bit different, and deduction actually failed here (because `&i`, as an `int*`, is indeed no kind of `T const*`). That would be pretty user-hostile (even if you think of this as an inconsistency in template deduction rules), because while you do correctly enforce deep constness, the lack of coercion makes that it's up to the user to do it:

```cpp
void f2(int i) {
    takes_ptr((int const*)&i);
}
```

Imagine having to do this at every call site where you call a function that takes a `T const*` or a `T const&`. 

The same problem holds with this declaration:

```cpp
template <contiguous_range R>
    requires constant_range<R>
void takes_contiguous_const_range(R&& r);
```

This accepts `vector<int> const` and `span<int const>`, but it rejects `vector<int>` and `span<int>`. The fact that it's a forwarding reference doesn't matter, the same issues are true with this approach:

```cpp
template <typename R>
    requires contiguous_range<R const>
          && constant_range<R const>
void takes_contiguous_const_range2(R const& r);
```

It's just that this way is more tedious to express (we have to pass `const R` into the concept, since that's the relevant type, and we don't have convenient syntax for it). And it also rejects different kinds of arguments that we still want to support... because we have non-`const`-iterable ranges (i.e. types `R` such that `R` is a `range` but `const R` is not a `range`). One such is:

```cpp
vector<int> const cv = {1, 2, 3};
takes_contiguous_range(cv);  // ok, is actually const
takes_contiguous_range2(cv); // ok, is actually const

takes_contiguous_range(cv | views::drop_while(p));  // ok
takes_contiguous_range2(cv | views::drop_while(p)); // error
```

So that's no kind of improvement.

### Enforcing deep const with a template, again

What you have to do instead is to basically do this manually:

```cpp
template <contiguous_range R>
void takes_contiguous_range3(R&& r) {
    // figure out what kind of span we want
    using V = range_value_t<R>;
    
    // and manually construct a const one
    takes_generic_const_span(span<V const>(r));
}
```

This is the same `takes_generic_const_span` function template I showed earlier and stated was almost completely useless. And that's still true - it's completely useless as a *user-facing* API. But it's useful here. The user calls `takes_contiguous_range3`, which simply requires contiguity (but cannot enforce const-ness, and as a result note that it is free to mutate elements internally if it so chose). This algorithm then itself coerces const-ness but adding it onto `r` and propagating it onto `takes_generic_const_span`, which then cannot mutate any elements. 

For instance, if you call this with a `vector<int>`, the call succeeds (`vector<int>` is indeed a contiguous range). The `value_type` is `int`, so we produce a `span<int const>` from that vector. Which is the same thing that happened in our non-generic `takes_const_span()` case, except that this one now also works with any other value type (like, say, `string`).

Similarly, invoking this algorithm works just fine with `vector<int> const` or `span<double>` or `v | views::drop_while(pred)`. 

### Enforcing deep const with a template, again again

But that's tedious. You have to manually write this conversion step. And, in this particular case, you want to make sure that you invoked a different function template (since any contiguous range of `int`s, whether const or not, should get funneled into the same specialization of `takes_generic_const_span`, which avoids instantiating more templates than necessary).

Even without `span`, there is still some benefit to avoiding template instantiations. For instance, you'd want to treat `list<int>` and `list<int> const` the same. But even separate from instantiations, there's the naming issue:

```cpp
template <range R>
void takes_any_range(R&& _r) {
    auto r = views::const_(_r);
}
```

See [my paper](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p2278r0.html#a-viewsconst_) for what `views::const_` is, based on what was in range-v3 under the same name.

Here, `r` is a constant range, for sure, regardless of whether `_r` was or not (if `_r` was already a constant range, we try to avoid instantiating anything further, so `r` may just be a view of `_r` directly - or a view of `as_const(_r)`).

And on the one hand, that's great. It's... easy to coerce const-ness, even if that coercion happens later than the function template signature where we usually expect it.

On the other hand, now we have two names in scope: `_r` and `r`. And we basically never want to actually use `_r` anymore in this algorithm, we really *just* want to use `r`. Naming the parameter `_r` (a @foonathan suggestion) might be good enough as something you would avoid accidentally using. But it would be nice to not even be able to use it by accident.

In some languages, this would not be a problem, we would have just written:

```cpp
template <range R>
void takes_any_range(R&& r) {
    // shadow the original r
    // or re-bind the name to a new object
    // whichever wording you prefer
    auto r = views::const_(r);
}
```

This is still arguably a little tedious because it's so manual, but at least now we would have removed any ability to accidentally mutate through the original range. But we can't do this in C++ anyway. What we can do is instead defer here in the same way that we deferred in the contiguous case:

```cpp
template <constant_range R>
void takes_any_range2_impl(R&& r) {
    // R is definitely a constant range
}

template <range R>
void takes_any_range2(R&& r) {
    takes_any_range2_impl(views::const_(r));
}
```

We can also take advantage of subsumption here and actually make this an overload set, since the `constant_range` concept subsumes the `range` one:

```cpp
template <constant_range R>
void takes_any_range2(R&& r) {
    // R is definitely a constant range
}

template <range R>
void takes_any_range2(R&& r) {
    takes_any_range2(views::const_(r));
}
```

### Is this something the language could help with

The answer to that question, in general, is probably yes.

There are at least two approaches here I can think of, although I am by no means suggesting that these are the only two possible solutions.

One is deduction guides for function templates, such that this:

```cpp
template <constant_range R>
void takes_any_range3(R&& r);

template <range R>
takes_any_range3(R&& r) -> takes_any_range3(views::const_(r));
```

Syntax doesn't matter, but the idea here would be that invoking `takes_any_range3(v)` where `v` is a `vector<int>` (mutable) would directly invoke `takes_any_range3` with a constant range (in this case, it would be a `ref_view<vector<int> const>`) without need for a second function template or more manual intervention. 

To be honest, I'm not even sure this is better at all than the manual solution of writing two function templates that I just showed -- it's like marginally less code while introducing a world of complexity with how function template deduction guides would even work. But it is some kind of solution so I thought it was worth mentioning anyway.

The other is C++0x (not C++20) concepts. While C++20 concepts only allow you to enforce semantics (as we saw when we tried to require `constant_range`), C++0x actually let you do more to alter interfaces. Again, don't worry about the syntax here too much, but had we been able to declare:

```cpp
template <typename R>
auto concept constant_range : range<R> {
    auto begin(R& r) {
        return make_const_iterator(possibly_const(r).begin());
    }
    
    auto end(R& r) {
        return make_const_sentinel(possibly_const(r).end());
    }
};
```

Then we would be able to write:

```cpp
template <constant_range R>
void takes_any_range4(R&&);
```

In this world, calling `begin` on `R` would go through the concept `constant_range` which would transform the result (if necessary) of calling `begin` on the underlying type. That is, even if the argument were a mutable range, the parameter would still be a constant one.

For instance:

```cpp
template <constant_range R>
void takes_any_range4(R&& r) {
    *r.begin() = 42;
}

vector<int> v = {1, 2, 3};
takes_any_range4(v); // error
```

This would fail, because `r.begin()` would not just be `v.begin()` (which would give you a mutable iterator because `v` is mutable) but rather end up giving you `std::as_const(v).begin()`, which is a constant iterator that you cannot assign through. 

This now becomes the perfect analogue of what we've always been able to do with normal references:

```cpp
template <typename T>
void takes_ref(T const& r) {
    r = 42;
}

int i;
takes_ref(i); // error
```

It may be syntactically quite different, but semantically it's the same: `takes_any_range4` can actually take any range but it both enforces and coerces const-ness internally, in a way that's clearly visible from the signature. Providing a mutable `std::string` still presents as if we provided a constant `std::string`.

### But for now

Until we have something like that (and I wouldn't hold my breath), the best bet to enforce and coerce const-ness for ranges is probably the two-step:

```cpp
template <constant_range R>
void takes_any_range2(R&& r) {
    // R is definitely a constant range
}

template <range R>
void takes_any_range2(R&& r) {
    takes_any_range2(views::const_(r));
}
```

Or simply write one function and stick with a naming convention (such as prefixed `_`) that helps you avoid unintentionally referring to the original object (with the downside that it may introduce further unnecessary template instantiations into your code):

```cpp
template <range R>
void takes_any_range2(R&& _r) {
    auto r = views::const_(_r);
    
    // r is definitely a constant range
    // never use _r again
}
```