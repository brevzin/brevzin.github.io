---
layout: post
title: "Implementing a better views::split"
category: c++
tags:
  - c++
  - c++20
---

One of the new additions to C++20 courtesy of Ranges is `views::split`  . There are two kinds of split supported: you can split by a single element or by a range of elements. This is an incredibly useful adapter since wanting to split things comes up fairly often. But there's a big problem with the specification here which has to do with how the inner range works.

Let's say we want to take a string like `"1.2.3.4"`   and turn it into a range of integers. You might expect to be able to write:

```cpp
std::string s = "1.2.3.4";

auto ints =
    s | views::split('.')
      | views::transform([](auto v){
            int i = 0;
            from_chars(v.begin(), v.end(), &i);
            return i;
        })
```

For the purposes of this post, I'm going to ignore error handling and just assume that we have only integers (as written above, any piece that's not an integer would end up yielding `0`  ). 

Now, we obviously can't use something like `atoi` because our pieces aren't going to be null terminated. But it turns out... we can't use `from_chars` either. gcc 10.1 informs us that:

<pre><b>split.cxx:10:21</b>: <font style="color:red"><b>error</b></font>: no matching function for call to ‘from_chars(std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_InnerIter&lt;true>, std::default_sentinel_t, int*)’
   10 |           <font style="color:red"><b>from_chars(v.begin(), v.end(), &i);</b></font>
      |           <font style="color:red"><b>~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~</b></font>
In file included from split.cxx:1:
<b>/usr/include/c++/10/charconv:588:5</b>: <font style="color:teal"><b>note</b></font>: candidate: ‘<b>template&lt;class _Tp> std::__detail::__integer_from_chars_result_type&lt;_Tp> std::from_chars(const char*, const char*, _Tp&, int)</b>’
  588 |     <font style="color:teal"><b>from_chars</b></font>(const char* __first, const char* __last, _Tp& __value,
      |     <font style="color:teal"><b>^~~~~~~~~~</b></font>
<b>/usr/include/c++/10/charconv:588:5</b>: <font style="color:teal"><b>note</b></font>:   template argument deduction/substitution failed:
<b>split.cxx:10:29</b>: <font style="color:teal"><b>note</b></font>:   cannot convert ‘v.std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_OuterIter&lt;true>::value_type::begin()’ (type ‘std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_InnerIter&lt;true>’) to type ‘const char*’
   10 |           from_chars(<font style="color:teal"><b>v.begin()</b></font>, v.end(), &i);
      |                      <font style="color:teal"><b>~~~~~~~^~</b></font></pre>

You might then think that oh, we're not suppose to pass iterators, we have to pass `v.data()`   and `v.data() + v.size()`  :

<pre><b>split.cxx:10:28</b>: <font style="color:red"><b>error</b></font>: no matching function for call to ‘std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_OuterIter&lt;true>::value_type::data()’
   10 |           from_chars(<font style="color:red"><b>v.data()</b></font>, v.data() + v.size(), &i);
      |                      <font style="color:red"><b>~~~~~~^~</b></font></pre>

The reason for the lack of `data()` is also spelled out:

<pre>In file included from split.cxx:2:
<b>/usr/include/c++/10/ranges:134:7</b>: <font style="color:teal"><b>note</b></font>: candidate: ‘constexpr auto std::ranges::view_interface&lt;_Derived>::data() requires  contiguous_iterator&lt;decltype(std::__detail::__ranges_begin((declval&lt;_Container&>)()))> [
  134 |       <font style="color:teal"><b>data</b></font>() requires contiguous_iterator&lt;iterator_t&lt;_Derived>>
      |       <font style="color:teal"><b>^~~~</b></font>
<b>/usr/include/c++/10/ranges:134:7</b>: <font style="color:teal"><b>note</b></font>: constraints not satisfied
In file included from /usr/include/c++/10/ranges:37,
                 from split.cxx:2:
<b>/usr/include/c++/10/concepts</b>: In instantiation of ‘constexpr auto std::ranges::view_interface&lt;_Derived>::data() requires  contiguous_iterator&lt;decltype(std::__detail::__ranges_begin((declval&lt;_Container&>)()))> [w
<b>split.cxx:10:28</b>:   required from ‘ints(const string&)::&lt;lambda(auto:13)> [with auto:13 = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::
<b>/usr/include/c++/10/type_traits:2506:26</b>:   required by substitution of ‘template&lt;class _Fn, class ... _Args> static std::__result_of_success&lt;decltype (declval&lt;_Fn>()((declval&lt;_Args>)()...)), std::__invoke_other>
<b>/usr/include/c++/10/type_traits:2517:55</b>:   required from ‘struct std::__result_of_impl&lt;false, false, ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::bas
<b>/usr/include/c++/10/type_traits:2961:12</b>:   recursively required by substitution of ‘template&lt;class _Result, class _Ret> struct std::__is_invocable_impl&lt;_Result, _Ret, true, std::__void_t&lt;typename _CTp::type> > [
<b>/usr/include/c++/10/type_traits:2961:12</b>:   required from ‘struct std::is_invocable&lt;ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >,
<b>/usr/include/c++/10/type_traits:3006:73</b>:   required from ‘constexpr const bool std::is_invocable_v&lt;ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic
<b>/usr/include/c++/10/concepts:338:25</b>:   required by substitution of ‘template&lt;class _Range, class _Fp> std::ranges::transform_view(_Range&&, _Fp)-> std::ranges::transform_view&lt;std::ranges::views::all_t&lt;_Range>, _
<b>/usr/include/c++/10/ranges:1978:73</b>:   required from ‘std::ranges::views::&lt;lambda(_Range&&, _Fp&&)> [with _Range = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::rang
<b>/usr/include/c++/10/ranges:1140:27</b>:   required from ‘std::ranges::views::__adaptor::_RangeAdaptor&lt;_Callable>::operator()&lt;{ints(const string&)::&lt;lambda(auto:13)>}>::&lt;lambda(_Range&&)> [with _Range = std::ranges::
<b>/usr/include/c++/10/ranges:1171:44</b>:   required from ‘constexpr auto std::ranges::views::__adaptor::operator|(_Range&&, const std::ranges::views::__adaptor::_RangeAdaptorClosure&lt;_Callable>&) [with _Range = std::r
<b>split.cxx:12:6</b>:   required from here
<b>/usr/include/c++/10/concepts:67:13</b>:   required for the satisfaction of ‘derived_from&lt;typename std::__detail::__iter_concept_impl&lt;_Iter>::type, std::bidirectional_iterator_tag>’ [with _Iter = std::ranges::split_v
<b>/usr/include/c++/10/bits/iterator_concepts.h:578:13</b>:   required for the satisfaction of ‘bidirectional_iterator&lt;_Iter>’ [with _Iter = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_strin
<b>/usr/include/c++/10/bits/iterator_concepts.h:588:13</b>:   required for the satisfaction of ‘random_access_iterator&lt;_Iter>’ [with _Iter = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_strin
<b>/usr/include/c++/10/bits/iterator_concepts.h:604:13</b>:   required for the satisfaction of ‘contiguous_iterator&lt;decltype (std::__detail::__ranges_begin(declval&lt;_Container&>()))>’ [with _Container = std::ranges::spl
<b>/usr/include/c++/10/concepts:67:28</b>: <font style="color:teal"><b>note</b></font>:   ‘std::bidirectional_iterator_tag’ is not a base of ‘std::forward_iterator_tag’
   67 |     concept derived_from = <font style="color:teal"><b>__is_base_of(_Base, _Derived)</b></font>
      |                            <font style="color:teal"><b>^~~~~~~~~~~~~~~~~~~~~~~~~~~~~</b></font></pre>


Basically, there is a `data()`   member on the iterator - but that member function has a constraint on the iterator being a contiguous iterator, and the iterator in question is _not_ a contiguous iterator because it's only a forward iterator. The last few lines of the error illustrate the path gcc is taking to check for constraint satisfication: in order to verify that it's a `contiguous_iterator`, we have to check `random_access_iterator`. In order to check that, we have to check `bidirectional_iterator`. And in checking `bidirectional_iterator`, we fail the iterator category check. 

But wait - we passed a contiguous range (a `std::string`  ) to `split` and only got a forward range back out? 

That right there is the premise of this blog post. The fact that in order to properly do this conversion you have to turn the underlying ranges into `std::string`  s yourself:

```cpp
auto ints =
    s | views::split('.')
      | views::transform([](auto v){
          return stoi(string(v.begin(), v.end()));
        });
}
```

Just kidding, that doesn't work either. 312 lines of error (go Chicago!) inform us that `v.begin()`   and `v.end()`   are different types while `std::string`  's constructor expects an iterator pair. So we have to first turn our sub-range into something that gives us an iterator/sentinel pair of the same type. We have `views::common`   for that:

```cpp
auto ints =
    s | views::split('.')
      | views::transform([](auto v){
          auto c = v | views::common;
          return stoi(string(c.begin(), c.end()));
        });
}
```

Which we could split (har har) into a part that yields a range of `std::string`   and then the part that does the integer conversion:

```cpp
auto split_strs = [](auto&& pattern){
    return views::split(FWD(pattern))
        | views::transform([](auto p){
              auto c = p | views::common;
              return string(c.begin(), c.end());
          });
};

auto ints =
    s | split_strs('.')
      | views::transform(stoi);
```

And actually that doesn't work either because `std::stoi`   has defaulted arguments so you can't pass it in directly into `views::transform`  , you have to write `[](std::string const& s) { return std::stoi(s); }`   instead. Is there a word for the total opposite of point-free programming? This is like the anti-Haskell.

Anyway, this is incredibly unsatisfying. If I have a `std::string`   or a `std::string_view`   that I'm splitting, I should be able to use `std::from_chars`   on the pieces.

## Why is it like this anyway?

Let's take a step back and consider Chesterton's fence:

> In the matter of reforming things, as distinct from deforming them, there is one plain and simple principle; a principle which will probably be called a paradox. There exists in such a case a certain institution or law; let us say, for the sake of simplicity, a fence or gate erected across a road. The more modern type of reformer goes gaily up to it and says, "I don't see the use of this; let us clear it away." To which the more intelligent type of reformer will do well to answer: "If you don't see the use of it, I certainly won't let you clear it away. Go away and think. Then, when you can come back and tell me that you do see the use of it, I may allow you to destroy it."

Why does `views::split`   work like this to begin with? Why doesn't it instead work something like this:

```cpp
template <viewable_range R>
    requires equality_comparable<range_value_t<R>>
auto split(R&& rng, range_value_t<R> value)
    -> generator<ranges::subrange<ranges::iterator_t<R>>>
{
    auto f = ranges::begin(rng);
    auto l = ranges::end(rng);
    while (f != l) {
        auto m = ranges::find(f, l, value);
        co_yield subrange(f, m);
        f = std::next(m, 1, l);
    }
}
```

And a little more complex for splitting on a range instead of a single element. Hopefully it's at least clear what's going on here, even if the implementation is wrong and if you (like me) are mostly unfamiliar with C++20 coroutines.

To start with, this implementation obviously can't support an `input_range` - we have to walk the range to find each delimiter and then yield back all the elements before that. C++20/range-v3's `views::split` does support `input_range`s!

The way that `views::split` supports `input_range`s is, fundamenally, the same reason that it doesn't give us contiguous subviews: `views::split` is maximally lazy. Instead of looking ahead for the next delimiter, the `split` in range-v3/C++20 just doesn't - instead it looks for the next delimiter as the inner range is advanced. 

Nominally, the reason for this is that you can always build a more eager algorithm on top of a lazy one. 

But I'm not sure that's the case here - since `views::split` doesn't give us the tools to do so. We need access to the underlying iterator of the view we're splitting - otherwise we can't go from `split_view`'s iterator to the underlying view's iterator to provide a subrange thereof. And even if we have that, it might not be enough. Consider:

```cpp
std::string input = "1.2.3.4";
auto parts = input | views::split('.');

auto f = ranges::begin(parts);
auto l = ranges::end(parts);
auto n = std::next(f);
```

At this point, a hypothetical `f.base()` would be pointing to the `1` while a hypothetical `n.base()` would be pointing to the `2`. `subrange(f.base(), n.base())` would thus be too long - that'd give us `"1."` so we'd need to back up a bit. Backing up suddenly requires a `bidirectional_range`, which is more range strengthening. Alternatively, `split_view`'s iterator needs to keep track of the beginning of the previous delimiter? I'm not sure how that would work at all.

One of the benefits of laziness as compared to eager lookahead might be that if the range that we're `split`ting is one built up such that either iteration is expensive (e.g. if it contains a `views::filter`) or dereferencing is expensive (e.g. if it contains a `views::transform`), we become much more inefficient due to the partial loss of laziness. We have to traverse the range twice - once to find the delimiter and once again if we actually want to traverse the yielded `subrange`. On the flip side, the laziness has its own set of costs as well. Consider:

```cpp
for (auto inner : split_view(rng, pattern)) {
    for (auto v : inner) {
        // ...
    }
}
```

This structure is seemingly optimal for a lazy view. But the issue here is that the inner iterator and the outer iterator _both_ have to compare against the `pattern` (the inner iterator does this in its `operator==(iterator, sentinel)` [\[range.split.inner\]/5](http://eel.is/c++draft/range.split#inner-5), while the outer iterator does this in its `operator++()` [\[range.split.outer\]/6](http://eel.is/c++draft/range.split#outer-6)). For the trivial case where we're splitting on a single value, this is just one extra comparison really but as the pattern gets longer, this might add up too... and might start eating into the benfeits of laziness to begin with. And if we do need to iterate over the inner range a second time for some reason... 

But... we don't have something that's just an `input_range`. And we don't have any expensive iteration or dereferencing here. We have a `std::string`   - those two operations are basically as cheap as you can get for a range that actually _does something_ (as opposed to, say, just infinitely returning the value `42`). Effectively, we're paying an abstraction penalty for functionality we don't need right now - and the functionality we _do_ need we can't easily build on top of this. 

## Can we do better?

One key different here is that `std::string`   is a *contiguous* range. While many of the range adapters can provide a random access range, the only range adapters that can provide a contiguous range are the ones that just slice off a part of the range: `r | views::take(n)`   and `r | views::drop(n)`   and their predicate-based relatives `r | views::take_while(pred)`   and `r | views::drop_while(pred)`  .

If we have a contiguous range, we don't have to worry about the costs of dereferencing and iteration, since a contiguous range more or less has to look like a pointer and length with no funny business. So let's go ahead and implement a split that only
supports a contiguous range, by yielding contiguous views. 

## Iterator Design

The main problem we have to solve is how our iterators are going to work. We have
one requirement that we have to keep in mind: `operator*()` has to be `const` (this comes from [`indirectly_readable`](http://eel.is/c++draft/iterator.concept.readable)). And `const` should really mean thread-safe, so we don't really want to have dereferencing itself look for the delimiter and stash the result into a `mutable iterator`. But we also don't want `operator*()` to search every time - so we need to have already found the end at that point.

But when do we find the end? We can't only do it in `operator++()`, because then we won't have a a value for the first one. So we need to have done it up front. But if we do it in `begin()` (i.e. by searching for the delimiter and then constructing our `split_view::iterator` from both the initial iterator and the first delimiter), then we run afoul of a different requirement: [`begin()` must be amortized constant time](http://eel.is/c++draft/ranges#range.range-3). The only way to really achieve _that_ is to cache the result of `begin` (non-modifying here refers to the platonic notion of the value of the range, not literally bitwise non-modifying). Doing that kind of caching requires modification, which means that `begin()` can't be `const`. 

So that's the plan here - we're going to cache the result of `begin()`, and not support const-iteration. 

The next question is - what is our iterator going to yield? What is its `reference` type - the result of `operator*() const`? A first approach might be:

```cpp
template <contiguous_range V, forward_range Pattern>
    requires view<V> && view<Pattern> &&
    indirectly_comparable<iterator_t<V>,
                          iterator_t<Pattern>,
                          equal_to>
class contig_split_view
    : public view_interface<contig_split_view<V, Pattern>>
{
    V base_ = V();
    Pattern pattern_ = Pattern();
    
public:
    struct iterator {
        using underlying = remove_reference_t<
            range_reference_t<V>>;
        using reference = span<underlying>;
    };
};
```

That is, just yield a `std::span<T>` for the right `T` (we do `std::remove_reference_t<std::ranges::range_reference_t<V>>` and not `std::ranges::range_value_t<V>` because if we're splitting something like a `std::string const&` we need to produce a `std::span<char const>`, not a `std::span<char>`).

Using a `span` is pretty good, but I want a little bit better. When I'm splitting a `std::string` (the most common case, really), I really do want a string-like thing back. But I don't want to get an entirely different kind of thing based on the container - I don't want to have one kind of split yield a `std::span<T>` but another kind yield a `std::string_view` (which works especially weirdly if splitting  `std::string` yielded a `std::span<char>` but splitting a `std::string const` yielded a `std::string_view` - and also worth noting that I think it's unfortunate that we don't have a mutable version of `std::string_view`). So I'm going to try to get the best of both worlds by yielding something that is basically a `span<T>` but also sometimes convertible to a `string_view`:

```cpp
struct reference : std::span<underlying> {
    using std::span<underlying>::span;
    
    operator std::string_view() const
        requires std::same_as<range_value_t<V>, char>
    {
        return {this->data(), this->size()};
    }
};
```

Okay, that gives us the result of `operator*()`. Now, let's talk about the rest of the shape of the iterator with a few more things we need to deal with.

We need to support iterator/sentinel ranges, so the easiest thing to do is just start off by adding a sentinel for ourselves:

```cpp
struct sentinel {
    sentinel_t<V> sentinel;
};
```

Pretty straightforward - our sentinel just wraps the base range's sentinel type. We'll put the `operator==` in the iterator.

Our iterator is going to have three things: (1) a pointer to our parent (since we need access to both the base range and the pattern), (2) an iterator pointing to the start of the current subrange, (3) an iterator pointing to the end of the current subrange. That allows for a very straightforward implementations of a bunch of the iterator members:

```cpp
class iterator {
private:
    contig_split_view* parent = nullptr;
    iterator_t<V> cur = iterator_t<V>();
    iterator_t<V> next = iterator_t<V>();

public:
    using iterator_category = std::forward_iterator_tag;
    struct reference { /* as before */ };
    using value_type = reference;
    using difference_type = std::ptrdiff_t;
    
    auto operator==(sentinel const& rhs) const -> bool {
        return cur == rhs.sentinel;
    }
    
    auto operator==(iterator const& rhs) const -> bool {
        return cur == rhs.cur;
    }
    
    auto operator*() const -> reference {
        return reference(cur, next);
    }
};
```

So far so good. Now we just need incrementing and a constructor:

```cpp
// default construction is required
iterator() = default;

// the actually useful constructor
iterator(contig_split_view* p)
    : parent(p)
    , cur(std::ranges::begin(p->base_))
    , next(lookup_next())
{ }
```

Where `lookup_next()` is used to find the endpoint of the current range. There's an algorithm for that: `search()`.

```cpp
auto lookup_next() const -> iterator_t<V> {
    return std::ranges::search(
        subrange(cur, std::ranges::end(parent->base_)),
        parent->pattern_
        ).begin();
}
```

Which `operator++()` (and its boilerplate cousin `operator++(int)`) just use. The only tricky thing here is that we have to skip over the delimiter when we get to it.

```cpp
auto operator++() -> iterator& {
    cur = next;
    if (cur != std::ranges::end(parent->base_)) {
        cur += distance(parent->pattern_);
        next = lookup_next();
    }
    return *this;
}
auto operator++(int) -> iterator {
    auto tmp = *this;
    ++*this;
    return tmp;
}
```

And that's... basically it, actually. Now we just need to wrap up our iterator/sentinel pair in the nice bow that is the `contig_split_view` itself (combined with caching `begin()`):

```cpp
template <contiguous_range V, forward_range Pattern>
    requires view<V> && view<Pattern> &&
    std::indirectly_comparable<iterator_t<V>,
                               iterator_t<Pattern>,
                               equal_to>
class contig_split_view
    : public view_interface<contig_split_view<V, Pattern>>
{
public:
    contig_split_view() = default;
    contig_split_view(V base, Pattern pattern)
        : base_(base)
        , pattern_(pattern)
    { }

    template <contiguous_range R>
	    requires std::constructible_from<V, views::all_t<R>>
	        && std::constructible_from<
                    Pattern, single_view<range_value_t<R>>>
	contig_split_view(R&& r, range_value_t<R> elem)
	    : base_(std::views::all(std::forward<R>(r)))
	    , pattern_(std::move(elem))
	{ }

    struct sentinel {
        sentinel_t<V> sentinel;
    };

    class iterator { /* ... */ };

    auto begin() -> iterator {
        if (not cached_begin_) {
            cached_begin_.emplace(this);
        }
        return *cached_begin_;
    }
    auto end() -> sentinel {
        return {std::ranges::end(base_)};
    }

private:
    V base_ = V();
    Pattern pattern_ = Pattern();
    std::optional<iterator> cached_begin_;
};
```

And there we have a perfectly functional split_view over a contiguous range that yields contiguous subranges (that even, when relevant, are convertible to `std::string_view`s).

Of course, the [extremely-naughty] icing on top of the cake is just to hijack `std::ranges::split_view` to refer to our implementation instead of the standard one. We do meet all the same requirements so this isn't exactly a `vector<bool>` kind of thing, and it means we can just use `std::views::split` directly:

```cpp
namespace std::ranges {
    template<contiguous_range V, forward_range Pattern>
    requires view<V> && view<Pattern>
      && indirectly_comparable<
        iterator_t<V>, iterator_t<Pattern>, equal_to>
    class split_view<V, Pattern>
        : public contig_split_view<V, Pattern>
    {
        using base = contig_split_view<V, Pattern>;
        using base::base;
    };
}
```
## Conditionally Common

With the above implementation, the iterator and sentinel types of our contiguous-supporting `split_view` are always different types (that is, we are not a `common_range`). That's fine if we only ever deal with code that supports that. But there's a lot of code out there that still requires the iterator and sentinel to be the same type. So we should allow that code to work where possible. In particular, we only really _need_ a sentinel type when our base range isn't a `common_range`. 

This is actually quite easy to support, since we already have our `iterator` satisfying `equality_comparable`. We just need to make `end()` return a different thing. To make instantiation a little cheaper, we'll also restructure a bit so that the `sentinel` owns `operator==(iterator, sentinel)` instead of the `iterator`:

```cpp
struct sentinel;
struct as_sentinel_t { };

class iterator {
private:
    friend sentinel;

    contig_split_view* parent = nullptr;
    iterator_t<V> cur = iterator_t<V>();
    iterator_t<V> next = iterator_t<V>();

public:
    iterator(as_sentinel_t, contig_split_view* p)
        : parent(p)
        , cur(std::ranges::end(p->base_))
        , next()
    { }
};

struct sentinel {
    bool operator==(iterator const& rhs) const {
        return rhs.cur == sentinel;
    }

    sentinel_t<V> sentinel;
};
```

and condition our implementation of `end()` (this could also be two different overloads but I find that `if constexpr` is almost always easier to understand):

```cpp
auto end() {
    if constexpr (common_range<V>) {
        return iterator(as_sentinel_t(), this);
    } else {
        return sentinel{std::ranges::end(base_)};
    }
}
```

## In action

Eh, voilà!

```cpp
for (std::string_view sv : "127..0..0..1"sv
                         | std::views::split(".."sv))
{
    // prints 127, then 0, then 0, then 1
    std::cout << sv << '\n';
}
```

And because this is a `common_range`, we can actually split a `std::string` into a `std::vector<std::string>`:

```cpp
auto ip = "127.0.0.1"s;
auto parts = ip | std::views::split('.');
auto as_vec = std::vector<std::string>(
    parts.begin(), parts.end());
```

But it still works just fine for those views that have a differing sentinel type:

```cpp
struct zstring_sentinel {
    bool operator==(char const* p) const {
        return *p == '\0';
    }
};

struct zstring : view_interface<zstring> {
    char const* p = nullptr;
    zstring() = default;
    zstring(char const* p) : p(p) { }
    auto begin() const { return p; }
    auto end() const { return zstring_sentinel{}; }
};

char const* words = "A quick brown fox";
for (std::string_view sv : zstring{words}
                         | std::views::split(' ')) {
    // prints those four words, newline separated
    std::cout << sv << '\n';
}
```

You can see the full thing on [Compiler Explorer](https://godbolt.org/z/nyWW3F).

## Conclusion

C++20's `views::split` is somewhat disappointing in that it isn't very ergonomic for the most common case: splitting a string. But we implement a more direct range adaptor for that case which is more along the lines of what a user would expect.

However, doing so we run into some issues. The issue specific to Ranges is that the iterator/sentinel model is a bit cumbersome for the kinds of algorithms like `split` where we want to push the next element at a time but we're in a model where we have to pull elements. It's not easy to invert your thinking to get a solution that fits all of the requirements (the combination of `begin()` being amortized constant and non-modifying and `operator*()` being `const`). This isn't at all a problem for algorithms like `transform` or things like... `take` or `drop`.

The bigger issue isn't Ranges-specific at all. Figuring out what the correct constraints were (or, rather, why my solution at various points in time did not meet those constraints) was remarkably difficult. One thing I didn't realize at first was that `operator*()` had to be `const`. Which, as a result, meant that my iterator wasn't an iterator and my range wasn't a range.

In trying to figure this out, I added `static_assert(forward_range<V>)` which led to this diagnostic:

<pre><b>&lt;source>:</b> In function '<b>int main()</b>':
<font style="color:blue"><b>&lt;source>:147:19</b></font>: <font style="color:red"><b>error</b></font>: <font style="color:blue">static assertion failed</font>
  147 |     static_assert(<font style="color:red"><b>forward_range&lt;V></b></font>);
      |                   <font style="color:red"><b>^~~~~~~~~~~~~~~~</b></font>
<font style="color:blue"><b>&lt;source>:147:19</b></font>: <font style="color:teal"><b>note:</b></font> <font style="color:blue">constraints not satisfied</font>
In file included from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/stl_iterator_base_types.h:71</b>,
                 from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/iterator:61</b>,
                 from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/ranges:44</b>,
                 from <b>&lt;source>:1</b>:
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:446:13</b>:   required for the satisfaction of '<b>__indirectly_readable_impl&lt;typename std::remove_cv&lt;typename std::remove_reference&lt;_Tp>::type>::type></b>' [with _Tp = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >::iterator&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >]
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:464:13</b>:   required for the satisfaction of '<b>indirectly_readable&lt;_Iter></b>' [with _Iter = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >::iterator&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >]
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:544:13</b>:   required for the satisfaction of '<b>input_iterator&lt;decltype (std::__detail::__ranges_begin(declval&lt;_Container&>()))></b>' [with _Container = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >]
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/range_access.h:909:13</b>:   required for the satisfaction of '<b>input_range&lt;_Tp></b>' [with _Tp = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >]
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:446:42</b>:   in requirements with '<b>const _In __in</b>' [with _Tp = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >::iterator&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >; _Tp = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >::iterator&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >; _In = contig_split_view&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >::iterator&lt;std::basic_string_view&lt;char, std::char_traits&lt;char> >, std::basic_string_view&lt;char, std::char_traits&lt;char> > >]
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:451:4</b>: <font style="color:teal"><b>note</b></font>: the required expression '<b>* __in</b>' is invalid
  451 |  { <font style="color:teal"><b>*__in</b></font> } -> same_as&lt;iter_reference_t&lt;_In>>;
      |    <font style="color:teal"><b>^~~~~</b></font>
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:452:21</b>: <font style="color:teal"><b>note</b></font>: the required expression '<b>std::ranges::__cust::iter_move(__in)</b>' is invalid
  452 |  { <font style="color:teal"><b>ranges::iter_move(__in)</b></font> } -> same_as&lt;iter_rvalue_reference_t&lt;_In>>;
      |    <font style="color:teal"><b>~~~~~~~~~~~~~~~~~^~~~~~</b></font>
cc1plus: <font style="color:teal"><b>note</b></font>: set '<b>-fconcepts-diagnostics-depth=</b>' to at least 2 for more detail</pre>

I was extremely confused about this diagnostic the first time I saw it, for several reasons.

First, it points out the problem with `*__in` but it's not actually obvious what `__in` means here. Easy enough to assume that it's my `iterator` type, and technically that appears somewhere in the diagnostic, but it's not obvious. This is hampered by what I would consider a clear diagnostic bug: the line introducing `const _In __in` introduces the definition of a type `_Tp` (twice!) before the definition of the type `_In` - but the type `_Tp` isn't relevant here (though it is long!)

Secondly, `iter_reference_t<In>` is literally defined as `decltype(*std::declval<In&>())` so it's not clear how those could be different types either (or why that requirement is specified). 

Third, the fact that `std::string_view` is expanded everywhere as `std::basic_string_view<char, std::char_traits<char> >` makes the diagnostic ludicrously verbose. Aliases are the bane of diagnostics. 

Fourth, the ordering changes halfway through. The hierarchy of concepts being checked goes bottom-to-top, but the specific lower-most concept that I'm failing is presented top-down.

When you add the suggested `-fconcepts-diagnostics-depth=2`, we get a little bit more info:

<pre><b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:451:4</b>: note: the required expression '<b>* __in</b>' is invalid, because
  451 |  { <font style="color:teal"><b>*__in</b></font> } -> same_as&lt;iter_reference_t&lt;_In>>;
      |    <font style="color:teal"><b>^~~~~</b></font>
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:451:4</b>: <font style="color:red"><b>error</b></font>: passing '<b>const contig_split_view&lt;std::basic_string_view&lt;char>, std::basic_string_view&lt;char> >::iterator</b>' as '<b>this</b>' argument discards qualifiers [<font style="color:red"><b>-fpermissive</b></font>]
<font style="color:blue"><b>&lt;source>:96:14:</b></font> <font style="color:teal"><b>note:</b></font>   <font style="color:blue">in call to '<b>contig_split_view&lt;V, Pattern>::iterator::reference contig_split_view&lt;V, Pattern>::iterator::operator*() [with V = std::basic_string_view&lt;char>; Pattern = std::basic_string_view&lt;char>]</b>'</font>
   96 |         auto <font style="color:teal"><b>operator</b></font>*() -> reference {
      |              <font style="color:teal"><b>^~~~~~~~</b></font></pre>
      
Here, at last, is the issue - we're trying to invoke `operator*()` on a `const` object but our `operator*()` isn't `const`-qualified. Technically, all of the information I needed to figure out my problem is in the diagnostic. But this was _not_ easy.

Instead, here is my re-imagined presentation of the above diagnostic with consistent ordering, substituting `std::string_view` in for the that type, and substituting the type into the concept itself. There are a few actual diagnostic bugs that I've fixed here as well (in one line `_Tp` appeared twice and my `iterator` is presented as a template for some reason). The main point here is to remove libstdc++'s names for parameters and present the diagnostic in a way that entirely refers to my types:

<pre><b>&lt;source>:</b> In function '<b>int main()</b>':
<font style="color:blue"><b>&lt;source>:147:19</b></font>: <font style="color:red"><b>error</b></font>: <font style="color:blue">static assertion failed</font>
  147 |     static_assert(<font style="color:red"><b>forward_range&lt;V></b></font>);
      |                   <font style="color:red"><b>^~~~~~~~~~~~~~~~</b></font>
<font style="color:blue"><b>&lt;source>:147:19</b></font>: <font style="color:teal"><b>note:</b></font> <font style="color:blue">constraints not satisfied</font>
In file included from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/stl_iterator_base_types.h:71</b>,
                 from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/iterator:61</b>,
                 from <b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/ranges:44</b>,
                 from <b>&lt;source>:1</b>:
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/range_access.h:909:13</b>:        required for the satisfaction of '<b>input_range&lt;contig_split_view&lt;std::string_view, std::string_view>></b>'
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:544:13</b>:   required for the satisfaction of '<b>input_iterator&lt;contig_split_view&lt;std::string_view, std::string_view>::iterator></b>'
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:464:13</b>:   required for the satisfaction of '<b>indirectly_readable&lt;contig_split_view&lt;std::string_view, std::string_view >::iterator></b>'
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:446:13</b>:   required for the satisfaction of '<b>__indirectly_readable_impl&lt;contig_split_view&lt;std::string_view, std::string_view >::iterator></b>'
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:446:42</b>:   in requirements with '<b>const contig_split_view&lt;std::string_view, std::string_view >::iterator __in</b>'
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:451:4</b>: <font style="color:teal"><b>note</b></font>: the required expression '<b>* __in</b>' is invalid
  451 |  { <font style="color:teal"><b>*__in</b></font> } -> same_as&lt;iter_reference_t&lt;contig_split_view&lt;std::string_view, std::string_view >::iterator>>;
      |    <font style="color:teal"><b>^~~~~</b></font>
<b>/opt/compiler-explorer/gcc-10.1.0/include/c++/10.1.0/bits/iterator_concepts.h:452:21</b>: <font style="color:teal"><b>note</b></font>: the required expression '<b>std::ranges::__cust::iter_move(__in)</b>' is invalid
  452 |  { <font style="color:teal"><b>ranges::iter_move(__in)</b></font> } -> same_as&lt;iter_rvalue_reference_t&lt;contig_split_view&lt;std::string_view, std::string_view >::iterator>>;
      |    <font style="color:teal"><b>~~~~~~~~~~~~~~~~~^~~~~~</b></font>
cc1plus: <font style="color:teal"><b>note</b></font>: set '<b>-fconcepts-diagnostics-depth=</b>' to at least 2 for more detail</pre>

There might be very good reasons why this is a bad approach, and it might very well cause more problems than it fixes. But I'm not sure the status quo is especially great either - I'm just used to it by now. 
