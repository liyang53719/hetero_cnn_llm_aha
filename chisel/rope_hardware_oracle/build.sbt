// SPDX-License-Identifier: Apache-2.0
ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "0.1.0"
val hf = file(sys.env("ROPE_HARDFLOAT_SOURCE"))
lazy val root = (project in file(".")).settings(
  name := "heteronpu-rope-hardware-oracle",
  libraryDependencies += "org.chipsalliance" %% "chisel" % "6.7.0",
  addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full),
  Compile / unmanagedSourceDirectories += hf / "hardfloat/src/main/scala",
  Compile / unmanagedSources ++= Seq("EmitHeteroFP32Alu.scala", "EmitHeteroFP32Pipelines.scala")
    .map(n => baseDirectory.value / "../../integration/gemmini" / n),
  scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked", "-language:reflectiveCalls")
)
