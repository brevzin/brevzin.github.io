---
layout: post
title: "Implementing a better views::split"
category: c++
pubdraft: yes
tags:
  - c++
  - c++20
---

One of the new additions to C++20 courtesy of Ranges is `views::split`{:.language-cpp}. There are two kinds of split supported: you can split by a single element or by a range of elements. This is an incredibly useful adapter since wanting to split things comes up fairly often. But there's a big problem with the specification here which has to do with how the inner range works.

Let's say we want to take a string like `"1.2.3.4"`{:.language-cpp} and turn it into a range of integers. You might expect to be able to write:

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

For the purposes of this post, I'm going to ignore error handling and just assume that we have only integers (as written above, any piece that's not an integer would end up yielding `0`{:.language-cpp}). 

Now, we obviously can't use something like `atoi` because our pieces aren't going to be null terminated. But it turns out... we can't use `from_chars` either. gcc 10.1 informs us that:

<pre>split.cxx:10:21: <font style="color:red">error</font>: no matching function for call to ‘from_chars(std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_InnerIter&lt;true>, std::default_sentinel_t, int*)’
   10 |           <font style="color:red">from_chars(v.begin(), v.end(), &i);</font>
      |           <font style="color:red">~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~</font>
In file included from split.cxx:1:
/usr/include/c++/10/charconv:588:5: <font style="color:teal">note</font>: candidate: ‘template&lt;class _Tp> std::__detail::__integer_from_chars_result_type&lt;_Tp> std::from_chars(const char*, const char*, _Tp&, int)’
  588 |     <font style="color:teal">from_chars</font>(const char* __first, const char* __last, _Tp& __value,
      |     <font style="color:teal">^~~~~~~~~~</font>
/usr/include/c++/10/charconv:588:5: <font style="color:teal">note</font>:   template argument deduction/substitution failed:
split.cxx:10:29: <font style="color:teal">note</font>:   cannot convert ‘v.std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_OuterIter&lt;true>::value_type::begin()’ (type ‘std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_InnerIter&lt;true>’) to type ‘const char*’
   10 |           from_chars(<font style="color:teal">v.begin()</font>, v.end(), &i);
      |                      <font style="color:teal">~~~~~~~^~</font></pre>

You might then thing that oh, we're not suppose to pass iterators, we have to pass `v.data()`{:.language-cpp} and `v.data() + v.size()`{:.language-cpp}:

<pre>split.cxx:10:28: <font style="color:red">error</font>: no matching function for call to ‘std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::_OuterIter&lt;true>::value_type::data()’
   10 |           from_chars(<font style="color:red">v.data()</font>, v.data() + v.size(), &i);
      |                      <font style="color:red">~~~~~~^~</font></pre>

The reason for the lack of `data()` is also spelled out:

<pre>In file included from split.cxx:2:
/usr/include/c++/10/ranges:134:7: <font style="color:teal">note</font>: candidate: ‘constexpr auto std::ranges::view_interface&lt;_Derived>::data() requires  contiguous_iterator&lt;decltype(std::__detail::__ranges_begin((declval&lt;_Container&>)()))> [
  134 |       <font style="color:teal">data</font>() requires contiguous_iterator&lt;iterator_t&lt;_Derived>>
      |       <font style="color:teal">^~~~</font>
/usr/include/c++/10/ranges:134:7: <font style="color:teal">note</font>: constraints not satisfied
In file included from /usr/include/c++/10/ranges:37,
                 from split.cxx:2:
/usr/include/c++/10/concepts: In instantiation of ‘constexpr auto std::ranges::view_interface&lt;_Derived>::data() requires  contiguous_iterator&lt;decltype(std::__detail::__ranges_begin((declval&lt;_Container&>)()))> [w
split.cxx:10:28:   required from ‘ints(const string&)::&lt;lambda(auto:13)> [with auto:13 = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::ranges::single_view&lt;char> >::
/usr/include/c++/10/type_traits:2506:26:   required by substitution of ‘template&lt;class _Fn, class ... _Args> static std::__result_of_success&lt;decltype (declval&lt;_Fn>()((declval&lt;_Args>)()...)), std::__invoke_other>
/usr/include/c++/10/type_traits:2517:55:   required from ‘struct std::__result_of_impl&lt;false, false, ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::bas
/usr/include/c++/10/type_traits:2961:12:   recursively required by substitution of ‘template&lt;class _Result, class _Ret> struct std::__is_invocable_impl&lt;_Result, _Ret, true, std::__void_t&lt;typename _CTp::type> > [
/usr/include/c++/10/type_traits:2961:12:   required from ‘struct std::is_invocable&lt;ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >,
/usr/include/c++/10/type_traits:3006:73:   required from ‘constexpr const bool std::is_invocable_v&lt;ints(const string&)::&lt;lambda(auto:13)>&, std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic
/usr/include/c++/10/concepts:338:25:   required by substitution of ‘template&lt;class _Range, class _Fp> std::ranges::transform_view(_Range&&, _Fp)-> std::ranges::transform_view&lt;std::ranges::views::all_t&lt;_Range>, _
/usr/include/c++/10/ranges:1978:73:   required from ‘std::ranges::views::&lt;lambda(_Range&&, _Fp&&)> [with _Range = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_string&lt;char> >, std::rang
/usr/include/c++/10/ranges:1140:27:   required from ‘std::ranges::views::__adaptor::_RangeAdaptor&lt;_Callable>::operator()&lt;{ints(const string&)::&lt;lambda(auto:13)>}>::&lt;lambda(_Range&&)> [with _Range = std::ranges::
/usr/include/c++/10/ranges:1171:44:   required from ‘constexpr auto std::ranges::views::__adaptor::operator|(_Range&&, const std::ranges::views::__adaptor::_RangeAdaptorClosure&lt;_Callable>&) [with _Range = std::r
split.cxx:12:6:   required from here
/usr/include/c++/10/concepts:67:13:   required for the satisfaction of ‘derived_from&lt;typename std::__detail::__iter_concept_impl&lt;_Iter>::type, std::bidirectional_iterator_tag>’ [with _Iter = std::ranges::split_v
/usr/include/c++/10/bits/iterator_concepts.h:578:13:   required for the satisfaction of ‘bidirectional_iterator&lt;_Iter>’ [with _Iter = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_strin
/usr/include/c++/10/bits/iterator_concepts.h:588:13:   required for the satisfaction of ‘random_access_iterator&lt;_Iter>’ [with _Iter = std::ranges::split_view&lt;std::ranges::ref_view&lt;const std::__cxx11::basic_strin
/usr/include/c++/10/bits/iterator_concepts.h:604:13:   required for the satisfaction of ‘contiguous_iterator&lt;decltype (std::__detail::__ranges_begin(declval&lt;_Container&>()))>’ [with _Container = std::ranges::spl
/usr/include/c++/10/concepts:67:28: <font style="color:teal">note</font>:   ‘std::bidirectional_iterator_tag’ is not a base of ‘std::forward_iterator_tag’
   67 |     concept derived_from = <font style="color:teal">__is_base_of(_Base, _Derived)</font>
      |                            <font style="color:teal">^~~~~~~~~~~~~~~~~~~~~~~~~~~~~</font></pre>


Basically, there is a `data()`{:.language-cpp} member on the iterator - but that member function has a constraint on the iterator being a contiguous iterator, and the iterator in question is _not_ a contiguous iterator because it's only a forward iterator. The last few lines of the error illustrate the path gcc is taking to check for constraint satisfication: in order to verify that it's a `contiguous_iterator`, we have to check `random_access_iterator`. In order to check that, we have to check `bidirectional_iterator`. And in checking `bidirectional_iterator`, we fail the iterator category check. 

But wait - we passed a contiguous range (a `std::string`{:.language-cpp}) to `split` and only got a forward range back out? 

That right there is the premise of this blog post. The fact that in order to properly do this conversion you have to turn the underlying ranges into `std::string`{:.language-cpp}s yourself:

```cpp
auto ints =
    s | views::split('.')
      | views::transform([](auto v){
          return stoi(string(v.begin(), v.end()));
        });
}
```

Just kidding, that doesn't work either. 312 lines of error (go Chicago!) inform us that `v.begin()`{:.language-cpp} and `v.end()`{:.language-cpp} are different types while `std::string`{:.language-cpp}'s constructor expects an iterator pair. So we have to first turn our sub-range into something that gives us an iterator/sentinel pair of the same type. We have `views::common`{:.language-cpp} for that:

```cpp
auto ints =
    s | views::split('.')
      | views::transform([](auto v){
          auto c = v | views::common;
          return stoi(string(c.begin(), c.end()));
        });
}
```

Which we could split (har har) into a part that yields a range of `std::string`{:.language-cpp} and then the part that does the integer conversion:

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

And actually that doesn't work either because `std::stoi`{:.language-cpp} has defaulted arguments so you can't pass it in directly into `views::transform`{:.language-cpp}, you have to write `[](std::string const& s) { return std::stoi(s); }`{:.language-cpp} instead. Is there a word for the total opposite of point-free programming? This is like the anti-Haskell.

Anyway, this is incredibly unsatisfying. If I have a `std::string`{:.language-cpp} or a `std::string_view`{:.language-cpp} that I'm splitting, I should be able to use `std::from_chars`{:.language-cpp} on the pieces.

## Why is it like this anyway?

Let's take a step back and consider Chesterton's fence:

> In the matter of reforming things, as distinct from deforming them, there is one plain and simple principle; a principle which will probably be called a paradox. There exists in such a case a certain institution or law; let us say, for the sake of simplicity, a fence or gate erected across a road. The more modern type of reformer goes gaily up to it and says, "I don't see the use of this; let us clear it away." To which the more intelligent type of reformer will do well to answer: "If you don't see the use of it, I certainly won't let you clear it away. Go away and think. Then, when you can come back and tell me that you do see the use of it, I may allow you to destroy it."

Why does `views::split`{:.language-cpp} work like this to begin with? Why doesn't it instead work something like this:

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
        f = m;
    }
}
```

This coroutine implementation might be wrong for one reason or another, but I'm just using this approach to get a more concise implementation. Hopefully it's at least clear what's going on here, even if the implementation is wrong and if you (like me) are mostly unfamiliar with C++20 coroutines.

To start with, this implementation obviously can't support an `input_range` - we have to walk the range to find each delimiter and then yield back a elements before that. C++20/range-v3's `views::split`{:.language-cpp} does support `input_range`s!

More importantly, if the range that we're `split`ting is one built up such that either iteration is expensive (e.g. if it contains a `views::filter`{:.language-cpp}) or dereferencing is expensive (e.g. if it contains a `views::transform`{:.language-cpp}), we become much more inefficient due to the partial loss of laziness. We have to traverse the range twice - once to find the delimiter and once again if we actually want to traverse the yielded `subrange`.

But... we don't have something that's just an `input_range`. And we don't have any expensive iteration or dereferencing here. We have a `std::string`{:.language-cpp} - those two operations are basically as cheap as you can get for a range that actually _does something_ (as opposed to, say, just infinitely returning the value `42`{:.language-cpp}). Effectively, we're paying an abstraction penalty for functionality we don't need right now. 

## Can we do better?

One key different here is that `std::string`{:.language-cpp} is a *contiguous* range. While many of the range adapters can provide a random access range, the only range adapters that can provide a contiguous range are the ones that just slice off a part of the range: `r | views::take(n)`{:.language-cpp} and `r | views::drop(n)`{:.language-cpp} and their predicate-based relatives `r | views::take_while(pred)`{:.language-cpp} and `r | views::drop_while(pred)`{:.language-cpp}.

If we have a contiguous range, we don't have to worry about the costs of dereferencing and iteration, since a contiguous range more or less has to look like a pointer and length with no funny business. 