"use strict";(self.webpackChunkdocs=self.webpackChunkdocs||[]).push([[863],{394:(e,t,n)=>{n.r(t),n.d(t,{assets:()=>r,contentTitle:()=>i,default:()=>u,frontMatter:()=>s,metadata:()=>c,toc:()=>d});var a=n(5893),o=n(1151);const s={sidebar_position:4,hide_table_of_contents:!0},i="Evaluation",c={id:"guides/core-types/evaluations",title:"Evaluation",description:"Evaluation-driven development helps you reliably iterate on an application. The Evaluation class is designed to assess the performance of a Model on a given Dataset using specified scoring functions.",source:"@site/docs/guides/core-types/evaluations.md",sourceDirName:"guides/core-types",slug:"/guides/core-types/evaluations",permalink:"/weave/guides/core-types/evaluations",draft:!1,unlisted:!1,editUrl:"https://github.com/facebook/docusaurus/tree/main/packages/create-docusaurus/templates/shared/docs/guides/core-types/evaluations.md",tags:[],version:"current",sidebarPosition:4,frontMatter:{sidebar_position:4,hide_table_of_contents:!0},sidebar:"documentationSidebar",previous:{title:"Datasets",permalink:"/weave/guides/core-types/datasets"},next:{title:"Tracking",permalink:"/weave/guides/tracking/"}},r={},d=[{value:"Parameters",id:"parameters",level:2}];function l(e){const t={code:"code",h1:"h1",h2:"h2",p:"p",pre:"pre",...(0,o.a)(),...e.components};return(0,a.jsxs)(a.Fragment,{children:[(0,a.jsx)(t.h1,{id:"evaluation",children:"Evaluation"}),"\n",(0,a.jsxs)(t.p,{children:["Evaluation-driven development helps you reliably iterate on an application. The ",(0,a.jsx)(t.code,{children:"Evaluation"})," class is designed to assess the performance of a ",(0,a.jsx)(t.code,{children:"Model"})," on a given ",(0,a.jsx)(t.code,{children:"Dataset"})," using specified scoring functions."]}),"\n",(0,a.jsx)(t.pre,{children:(0,a.jsx)(t.code,{className:"language-python",children:"evaluation = evaluate.Evaluation(\n    dataset, scores=[score], example_to_model_input=example_to_model_input\n)\nprint(asyncio.run(evaluation.evaluate(model)))\n"})}),"\n",(0,a.jsx)(t.h2,{id:"parameters",children:"Parameters"}),"\n",(0,a.jsxs)(t.p,{children:[(0,a.jsx)(t.code,{children:"dataset"}),": A ",(0,a.jsx)(t.code,{children:"Dataset"})," with a collection of examples to be evaluated\n",(0,a.jsx)(t.code,{children:"scores"}),": A list of scoring functions. Each function should take an example and a prediction, returning a dictionary with the scores.\n",(0,a.jsx)(t.code,{children:"example_to_model_input"}),": A function that formats each example into a format that the model can process.\n",(0,a.jsx)(t.code,{children:"model"}),": pass this to ",(0,a.jsx)(t.code,{children:"evaluation.evaluate"})," to run ",(0,a.jsx)(t.code,{children:"predict"})," on each example and score the output with each scoring function."]})]})}function u(e={}){const{wrapper:t}={...(0,o.a)(),...e.components};return t?(0,a.jsx)(t,{...e,children:(0,a.jsx)(l,{...e})}):l(e)}},1151:(e,t,n)=>{n.d(t,{Z:()=>c,a:()=>i});var a=n(7294);const o={},s=a.createContext(o);function i(e){const t=a.useContext(s);return a.useMemo((function(){return"function"==typeof e?e(t):{...t,...e}}),[t,e])}function c(e){let t;return t=e.disableParentContext?"function"==typeof e.components?e.components(o):e.components||o:i(e.components),a.createElement(s.Provider,{value:t},e.children)}}}]);