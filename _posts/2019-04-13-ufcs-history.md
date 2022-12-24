---
layout: post
title: "What is unified function call syntax anyway?"
category: c++
series: ufcs
tags:
 - c++
 - c++17
 - ufcs
--- 

One of the language proposals in the last few years that comes up fairly regularly is Unified Function Call Syntax, sometimes also called Unified Call Syntax. I'm going to use the former name, abbreviated as UFCS, because FLAs are the new TLAs.

What makes this particular proposal confusing in these kinds of discussions is that it's not really _one_ proposal - it's multiple different proposals under the same umbrella. And I've found that people often discuss UFCS as if it's one thing, but are actually talking about different flavors of it, despite all speaking with total certainty about what _the_ UFCS proposal was. In the interest of alleviating that confusion, I wanted to write a post expounding on all the different variations of proposals in that space. My goal here isn't to argue for or against UFCS, simply to explain what it is (or more accurately, what they are).

There are two axes of orthogonal decisions to be made in this space:

- How are we expanding the candidate set?
- How are we going to change the overload resolution rules to pick between the old candidates and the new candidates?

I'll go through these in turn.

### Candidate Set Options

There are broadly two orthogonal choices here: whether free function syntax can find member functions, and whether member function syntax can find free functions.

CS:FreeFindsMember) We could allow non-member call syntax to find member functions:

```cpp
struct X {
    void f(Y);
};

// ill-formed today, but with CS:FreeFindsMember would
// be able to call x.f(y)
f(x, y);
```

CS:MemberFindsFree) We could allow member call syntax to find non-member functions:

```cpp
struct X { };
void g(X, Y);

// ill-formed today, but with CS:MemberFindsFree would
// be able to call g(x, y)
x.g(y);
```

CS:AnyFindsAny) We could do both of the above.

CS:ExtensionMethods) We could add a special syntax to declare non-member functions to be usable with member function syntax. This is a kind of opt-in CS:MemberFindsFree:  the free function must be specially annotated:

```cpp
struct B { };
void bar(this B&, int x);
b.bar(1); // invokes bar(b, 1);
```

It's important to point out that these are all different.

### Overload Resolution Rules

In the mundane cases, either only the existing candidates exist or only the new candidates we add exist, so we don't have to think about which one we choose. But this being C++, we always have to deal with the exception cases. So the question is - what do we do if there's both a new and existing candidate? How do we pick?

We, again, have multiple options. Again, there are two broad choices: do we do a single round of overload resolution with all the candidates, or do we do two rounds of overload resolution with a fallback step? If we do a single round, how do we resolve ambiguities between the different kinds of candidate sets (if at all)? If we do two rounds of overload resolution, which one do we do first?

OR:TwoRoundsPreferAsWritten) We could prefer the candidate with syntax as written. That is, do overload resolution the old way and only if no candidate is found, then look up the new candidates. Non-member syntax would look up only free functions first. Member syntax would look up only member functions first.

OR:TwoRoundsMemberFirst) We could always prefer the member function syntax, regardless of how the code is writen. That is, same as OR:TwoRoundsPreferAsWritten, but treat non-member calls as member calls first.

OR:OneRound) We could consider all the candidates together and perform one overload resolution round on the whole set.

OR:OneRoundPreferMembers) Same as above... but prefer member functions to non-member functions as a tiebreaker, in case of ambiguity.

Here's a short code fragment demonstrating the differences between the approaches:

```cpp
struct A {
    A(int);
    operator int() const;
};

struct X {
    void f(A);
    void g(int);
    void h(int);
};
void f(X, int);
void g(X, A);
void h(X, int);

// OR:TwoRoundsPreferAsWritten: calls ::f(X, int)
// OR:OneRound: calls X::f(A)
// OR:TwoRoundsMemberFirst: calls X::f(A)
f(x, a);

// OR:TwoRoundsPreferAsWritten: calls X::g(int)
// OR:OneRound: calls ::g(X, A)
// OR:TwoRoundsMemberFirst: calls X::g(int)
x.g(a);

// OR:TwoRoundsPreferAsWritten:
//      calls ::h for former, X:::h for latter
// OR:OneRound: both ambiguous
// OR:OneRoundPreferMembers: both call X::h
// OR:TwoRoundsMemberFirst: both call X::h
h(x, 0);
x.h(0);
```
These overload resolution options aren't completely orthogonal to the candidate set rules, since OR:TwoRoundsMemberFirst doesn't apply with CS:MemberFindsFree - since that one only makes sense if the non-member call syntax can find member functions.

A fun example, of why changing overload resolution is hard, courtesy of Herb Sutter (assuming non-member syntax can find member functions):

```cpp
struct X { void f(); }; // 1
void f(X);              // 2

f(x); // today: calls 2 (it's the only candidate)
      // OR:TwoRoundsPreferAsWritten: calls 2, as today
      // OR:OneRound:                 error ambiguous
      // OR:OneRoundPreferMembers:    calls 1
      // OR:TwoRoundsMemberFirst:     calls 1
```

A reverse example (assuming member syntax can find non-member functions):

```cpp
struct Y {
   template <typename T> void g(T); // 1
};
void g(Y, int); // 2

y.g(42); // today: calls 1 (it's the only candidate)
         // OR:TwoRoundsPreferAsWritten: calls 1
         // OR:OneRound:                 calls 2
         // OR:TwoRoundsMemberFirst:     calls 1
```

### History of Papers

There were a bunch of papers in this space, hopefully this is the full list:

- [N1585](https://wg21.link/n1585) (Glassborow, Feb 2004): CS:ExtensionMethods, OR:OneRoundPreferMembers.
- [N4165](https://wg21.link/n4165) (Sutter, Oct 2014): CS:MemberFindsFree, OR:TwoRoundsPreferAsWritten.
- [N4174](https://wg21.link/n4174) (Stroustrup, Oct 2014): This was more an exploration of the space, but argues for OR:TwoRoundsMemberFirst.
- [N4474](https://wg21.link/n4474) (Stroustrup and Sutter, Apr 2015): CS:AnyFindsAny, OR:TwoRoundsPreferAsWritten.
- [P0079R0](https://wg21.link/p0079r0) (Coe and Orr, Sep 2015): CS:ExtensionMethods, OR:TwoRoundsPreferAsWritten.
- [P0131R0](https://wg21.link/p0131r0) (Stroustrup, Sep 2015): Just a discussion of concerns presented with UFCS as a whole. 
- [P0251R0](https://wg21.link/p0251r0) (Stroustrup and Sutter, Feb 2016): CS:FreeFindsMember, OR:TwoRoundsPreferAsWritten. 
- [isocpp.org blog](https://isocpp.org/blog/2016/02/a-bit-of-background-for-the-unified-call-proposal): A post written by Stroustrup itself containing a bunch of history of this feature set and justification for pursuing CS:FreeFindsMember, OR:TwoRoundsPreferAsWritten.
- [P0301R0](https://wg21.link/p0301r0) (Maurer, Mar 2016): Wording paper for P0251. CS:FreeFindsMember, OR:TwoRoundsPreferAsWritten.
- [P0301R1](https://wg21.link/p0301r1) (Maurer, Mar 2016): This paper actually introduces a new function call introducer such that `.f(x, y)`{:.language-cpp} is the merged overload set (OR:OneRoundPreferMembers) of `f(x, y)`{:.language-cpp} and `x.f(y)`{:.language-cpp}, with `.x.f(y)`{:.language-cpp} being equivalent to `.f(x, y)`{:.language-cpp}.

As you can see, there are lots of _different_ proposals here. One of them (P0301R0) went up for a vote in the Jacksonville meeting in March 2016 (non-member call syntax finds member functions only). You can see the results of that vote in the [minutes](https://wg21.link/n4586). The initial vote was:

<table style="text-align:center">
<tr><th>For</th><th>Abstain</th><th>Against</th></tr>
<tr><td>24</td><td>21</td><td>24</td></tr>
</table>

After some discussion, a five-way poll was taken:

<table style="text-align:center">
<tr><th>SF</th><th>F</th><th>N</th><th>A</th><th>SA</th></tr>
<tr><td>13</td><td>11</td><td>18</td><td>21</td><td>5</td></tr>
</table>

This failed to reach consensus and was rejected. As far as I'm aware, nobody has done work on it since.

### Where do we go from here?

Between all of the above papers, there are multiple problems trying to be solved, with multiple approaches to solving them, and multiple issues being brought up. If UFCS is important to you, that history needs to be addressed.

But most importantly, I would like to make sure that when we talk about UFCS, we make sure that first we agree on what we're actually talking about. 
