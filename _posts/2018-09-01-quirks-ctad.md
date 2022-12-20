---
layout: post
title: "Quirks in Class Template Argument Deduction"
category: c++
tags:
 - c++
 - c++17
--- 

Before C++17, template deduction [basically] worked in two situations: deduction function parameters in function templates and deducing `auto`{:.language-cpp} for variables/return types in functions. There was no mechanism to deduce template parameters in class templates.

The result of that was— whenever you used a class template, you either had to (1) explicitly specify the template parameters or (2) write a helper `make_*()`{:.language-cpp} function that does the deduction for you. In the former case, it’s either repetitive/error-prone (if we’re just providing exactly the types of our arguments) or impossible (if our argument is a lambda). In the latter case, we have to know what those helpers are... they’re not always named <code class="language-cpp">make_*()</code>. The standard has <code class="language-cpp">make_pair()</code>, <code class="language-cpp">make_tuple()</code>, and <code class="language-cpp">make_move_iterator()</code>... but also <code class="language-cpp">inserter()</code> and <code class="language-cpp">back_inserter()</code> for instance.

Class template argument deduction changed that by allowing class template arguments to be deduced by way of either the constructors of the primary class templates or deduction guides. The end result is that we can write code like:

```cpp
pair p(1, 2.0);     // pair<int, double>
tuple t(1, 2, 3.0); // tuple<int, int, double>

template<class Func>
class Foo() { 
public: 
    Foo(Func f) : func(f) {} 
    void operator()(int i) const { 
      std::cout << "Calling with " << i << endl;
      f(i); 
    } 
private: 
    Func func; 
};
for_each(vi.begin(), vi.end(),
    Foo([&](int i){...})); // Foo<some_lambda_type>
```

No types explicitly specified here. No need for using <code class="language-cpp">make_*()</code>, even for lambdas.

<hr />

However, there are two quirks of class template argument deduction (hereafter, CTAD) that are worth keeping in mind.

The first is that, this is the first time in the language where we can have two variable declarations that look like they’re declaring the same type but are not:

```cpp
// both auto, but no expectation of same type
auto a = 1;
auto b = 2.0;

// both std::pair, which looks like it's a type
// but isn't, different types
std::pair c(1, 2);
std::pair d(1, 2.0);
```

When we use <code class="language-cpp">auto</code>, there’s no expectation that this is a type at all. But when we use the name of a primary class template, we have to stop and think for a bit. Sure, with <code class="language-cpp">std::pair</code> it’s obvious that this isn’t a type - this is a well-known class template. But with user-defined types, it may not be so obvious. In the above example, `c` and `d` look like they’re objects of type <code class="language-cpp">std::pair</code> - and thus are of the same type. But they’re actually objects of type `std::pair<int,int>`{:.language-cpp} and <code class="language-cpp">std::pair&lt;int,double&gt;</code> respectively.

(**update**: it was correctly pointed out by /u/cpp_learner that this is not the first such case due to the existence of arrays of unknown bound. However, I suspect that CTAD will be used far, far more often than that so I think it’s at least far to say that (a) this will be the first _commonly used_ time that this holds and (b) arrays of unknown bounds are more obviously placeholder types than names of class templates).

We’ll get this same issue in C++20 with the adoption of Concepts. And the [YAACD paper](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1141r0.html) actually points to CTAD as a reason for supporting <code class="language-cpp">Concept name = ...</code> over <code class="language-cpp">Concept auto name = ...</code>:

> In variable declarations, omitting the auto also seems reasonable:
> 
```cpp
Constraint x = f2();
```
> Note, in particular, that we already have a syntax that does (partial) deduction but doesn’t make that explicit in the syntax:
> 
```cpp
std::tuple x = foo();
```

This using-placeholder-that-looks-like-a-type-but-isn’t issue isn’t going to go away. Quite the opposite, it’s going to become much more common. So it’s just something to keep in mind.

<hr />

The second quirk is, to me, a much bigger issue and one that is meaningfully different between Concepts and CTAD and comes from exactly what problem it is that we’re trying to solve.

The motivation for CTAD as expressed in every draft of the paper is very much: I want to construct a specialization of a class template without having to explicitly specify the template parameters - just deduce them for me so I don’t have to write helper factories or look up what they are. That is, I want to _construct a new thing_.

The motivation for Concepts is broader, but specifically in the context of constrained variable declarations is: I want to construct an object whose type I don’t care about, but rather than using <code class="language-cpp">auto</code>, I want to express a more specific set of requirements for this type. That is, I’m still using the existing type, I’m just adding an _annotation_.

At least that’s how I think about it.

These two ideas may not seem like they clash, but they do. And it may not appear that we’re making a choice between two things, but we are. This conflict is expressed by a recent twitter thread:

<blockquote class="twitter-tweet" data-conversation="none" data-lang="en"><p lang="en" dir="ltr">Most programmers would expect “tuple dest(src)” and “auto dest(src)” to do the same thing.</p>&mdash; Stephan T. Lavavej (@StephanTLavavej) <a href="https://twitter.com/StephanTLavavej/status/1032695948953116672?ref_src=twsrc%5Etfw">August 23, 2018</a></blockquote>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
<blockquote class="twitter-tweet" data-conversation="none" data-lang="en"><p lang="en" dir="ltr">Most programmers expect the behavior of &quot;tuple(args...)&quot; not to depend on the number of args. Most programmers don&#39;t know those two expectations are conflicting.</p>&mdash; Casey Carter (@CoderCasey) <a href="https://twitter.com/CoderCasey/status/1032696710890512384?ref_src=twsrc%5Etfw">August 23, 2018</a></blockquote>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
<blockquote class="twitter-tweet" data-conversation="none" data-lang="en"><p lang="en" dir="ltr">Most programmers aren’t most programmers. 🤔</p>&mdash; JF Bastien (@jfbastien) <a href="https://twitter.com/jfbastien/status/1032696909448732672?ref_src=twsrc%5Etfw">August 23, 2018</a></blockquote>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>

Never quit, JF. Never quit.

The issue boils down to: what does this do, exactly:

```cpp
std::tuple<int> foo();

std::tuple x = foo();
auto y = foo();
```

What is the intent behind the declaration of variable `x`? Are we constructing a new thing (the CTAD goal) or are we using <code class="language-cpp">std::tuple</code> as annotation to ensure that `x` is in fact a `tuple` (the Concepts goal)?

STL makes the point that most programmers would expect `x` and `y` to have the same meaning. But this kind of annotation wasn’t the goal of CTAD. CTAD was about creating new things - which suggests that while `y` is clearly a <code class="language-cpp">tuple&lt;int&gt;</code>, `x` needs to be a <code class="language-cpp">tuple&lt;tuple&lt;int&gt;&gt;</code>. That is, after all, what we’re asking for. We’re creating a new class template specialization based on our arguments?

This conflict becomes clearer in this example:

```cpp
// The tuple case
// unquestionably, tuple<int>
std::tuple a(1);

// unquestionably, tuple<tuple<int>,tuple<int>>
std::tuple b(a, a);

// ??
std::tuple c(a);

/////////////////////////////////////////////////
// The vector case
// unquestionably, vector<int>
std::vector x{1};

// unquestionably, vector<vector<int>>
std::vector y{x, x};

// ??
std::vector z{x};
```

This is the point that Casey made. Is `c` a <code class="language-cpp">tuple&lt;int&gt;</code> or a <code class="language-cpp">tuple&lt;tuple&lt;int&gt;&gt;</code>? Is `z` a <code class="language-cpp">vector&lt;int&gt;</code> or a <code class="language-cpp">vector&lt;vector&lt;int&gt;&gt;</code>?

In C++17, if we’re using CTAD with a copy, the copy takes precedence. This means that the single-argument case effectively follows a different set of rules than the multi-argument case. In C++17, `c` is a <code class="language-cpp">tuple&lt;int&gt;</code> and `z` is a <code class="language-cpp">vector&lt;int&gt;</code>, each just copy-constructing its argument.

In other words, to Casey’s point, the type of <code class="language-cpp">tuple(args...)</code> depends not only on the number of arguments but also their type. That is:

- If <code class="language-cpp">sizeof...(args) != 1</code>: <code class="language-cpp">tuple&lt;decay_t&lt;decltype(args)&gt;...&gt;</code>
- Otherwise, if `args0` is not a specialization of tuple: <code class="language-cpp">tuple&lt;decay_t&lt;decltype(arg0)&gt;&gt;</code>
- Else, <code class="language-cpp">decay_t&lt;decltype(arg0)&gt;</code>

That’s decidedly not simple. (Also there's another case where we deduce from <code class="language-cpp">std::pair</code>).

I think this is an unfortunate and unnecessary clash - especially in light of the imminent arrival of Concepts, that would allow us to easily distinguish between the two cases:

```cpp
template <typename T, template <typename...> class Z>
concept Specializes = ...;

// The tuple case
// unquestionably, tuple<int>
tuple a(1);

// unquestionably, tuple<tuple<int>, tuple<int>>
tuple b(a, a);
// tuple<tuple<int>>
tuple c(a);
// tuple<int>
Specializes<tuple> d(a);

/////////////////////////////////////////////////
// The vector case
// unquestionably, vector<int>
vector x{1};

// unquestionably, vector<vector<int>>
vector y{x, x};

// vector<vector<int>>
vector z{x};

// vector<int>
Specializes<vector> w{x};
```

Here, we would use each language feature for the thing it does best: constructing new things for CTAD, and constraining existing things for Concepts.

<hr />

But these are the rules we have in C++17, and those won't change, so it’s important to keep in mind that these quirks exist. Especially the second one - which means you need to be very careful when you use CTAD in generic code:

```cpp
template <typename... Ts>
auto make_vector(Ts... elems) {
    std::vector v{elems...};
    assert(v.size() == sizeof(elems)); // right??
    return v;
}

auto a = make_vector(1, 2, 3); // ok
auto b = make_vector(1);       // ok
auto c = make_vector(a, b);    // ok
auto d = make_vector(c);       // assert fires
```