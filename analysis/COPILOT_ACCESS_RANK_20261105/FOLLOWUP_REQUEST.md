# Focused correction to the proposed next test

Continue the explicitly authorized independent technical review for
IgorSabirov/vm-lab. Answer in Russian; no tools or numerical runs. This is
a fresh process: all necessary context is below. Do not invent a model or
adopt a scientific next step for the user.

In your prior answer you correctly separated:
- exact finite BFS of (pointer x, reserve support Q, used-label set U),
- reproduction of access tokens under an input copying rule,
- observability through an explicit output/record history.

But in Q5 you proposed this as the one minimal bridge test:
«для впервые добавленного в резерв типа проверить, меняет ли соответствующий
доступ D, определён ли он из текущего указателя и остаётся ли после него хотя
бы один исполнимый переход. Это один локальный тест связи
“сгенерированный доступ — различение — продолжение”».

Please independently recheck this proposal, not just assent to our objection.

Definitions: f is a partial binary operation. Full profile
P(x)=((f(x,z))_z,(f(z,x))_z), including undefinedness and exact output labels.
D(x,y) iff P(x)!=P(y). A previously defined 'active' a has a pair x,y, both
f(x,a),f(y,a) defined, such that D(x,y)!=D(f(x,a),f(y,a)).

Our objection 1: if D(x,y)=0, their rows already agree, hence f(x,a)=f(y,a)
whenever defined. Therefore active access under this definition can ONLY
change D from 1 to 0. No associativity is needed. This is erasure/merging,
not acquisition of an independently distinguishable output. It can be a
valid test of noninjectivity, but it does not establish the requested bridge
to increasing informational rank. A bijective group translation never
passes this active-access test, although its repeated action under a fixed
noninjective observation can give an injective output history.

Explicit example: X={0,1,2}, T(x)=x+1 mod3, O(0)=1,O(1)=O(2)=0.
Three-sample histories are (1,0,0),(0,0,1),(0,1,0); indeed already the
two-sample histories (O(x),O(Tx)) distinguish all three states. O is added,
not derived from the operation. Thus the numeral three is not the bridge.

Our objection 2: having one further enabled event is only one-step
nonblocking; that event can lead to a dead end. It does not establish
repeatable availability. In a finite exact transition graph, a reachable
nonterminal directed cycle establishes existence of an infinite executable
path, but not autonomous schedule selection, stability, or replenishment
of physically consumed resources. Here all token reserves grow by rule.

Questions:
1. Are these objections correct? Give a counterexample if either is not.
2. Does your Q5 test need to be withdrawn as a bridge to information
   completeness, while remaining a possible noninjectivity check?
3. State the exact meaningful comparison WITHOUT adding an arbitrary
   injective observation: if an independently specified internal output O
   and permitted execution policy/words are supplied, compare the equivalence
   classes of initial states induced by finite output histories, while
   separately checking those operations remain executable. Until O/records
   and execution semantics are specified, is the desired bridge underdetermined?
4. One more qualification: your Q3 lower bound of five events for one-role
   aliasing in Z3 was compressed. With identity normalized to 0, initial
   pointer s!=0, q=0, x'=x+a, q'=q+e_a, explain briefly why 3 and 4 events
   cannot both close the pointer and use 0,s,-s. A 3-event closed word uses
   each label once; a 4-event closed word must repeat 0. This concerns
   these guards and this goal, not a universal minimum.

Conclude with a short replacement for Q5, and explicitly list any corrected
statement. Do not claim any census has been rerun. Fixed laws do not rule
out internal physical production; full-rank observation does not establish
the origin of its instruments or a correcting agent.
